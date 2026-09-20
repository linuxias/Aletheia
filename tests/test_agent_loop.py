import json
import threading
import time

import pytest

from config import Config
from core.agent import Agent
from core.llm.base import LLMClient
from core.llm.events import TextDelta, ToolCall
from core.tools.base import Tool
from core.tools.registry import ToolRegistry


class FakeLLMClient(LLMClient):
    """LLMClient whose stream() replays scripted event batches.

    Batches may be exception instances (raised when the batch is reached).
    When the batches run out, `repeat` (if set) is replayed forever.
    """

    protocol_name = "fake"
    DEFAULT_BASE_URL = "http://localhost"

    def __init__(self, batches, repeat=None):
        self.batches = list(batches)
        self.repeat = repeat
        self.calls = []  # (messages, tools) per stream() invocation

    def _new_sdk_client(self, api_key, base_url):
        return None

    def stream(self, *, model, max_tokens, system, messages, tools=None):
        self.calls.append((list(messages), tools))
        if self.batches:
            batch = self.batches.pop(0)
        elif self.repeat is not None:
            batch = self.repeat
        else:
            raise AssertionError("FakeLLMClient ran out of scripted batches")
        if isinstance(batch, BaseException):
            raise batch
        yield from batch


def _agent(client, registry=None, approver=None):
    return Agent(
        system_prompt="test",
        client=client,
        tools=registry,
        approver=approver,
    )


def test_text_only_turn_keeps_str_history():
    agent = _agent(FakeLLMClient([[TextDelta("hi")]]))
    assert agent.run("hello") == "hi"
    assert agent.messages == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    assert agent.client.calls[0][1] is None  # no registry: no tools passed


def test_tool_round_trip(tmp_path):
    p = tmp_path / "note.txt"
    p.write_text("needle line\n")
    registry = ToolRegistry()
    from core.tools.read import ReadTool

    registry.register(ReadTool())

    client = FakeLLMClient(
        [
            [
                TextDelta("checking"),
                ToolCall(id="t1", name="Read", arguments=json.dumps({"file_path": str(p)})),
            ],
            [TextDelta("it contains a needle")],
        ]
    )
    agent = _agent(client, registry)
    out = agent.run("what is in the note?")

    assert out == "it contains a needle"
    assert agent.messages[1]["content"] == [
        {"type": "text", "text": "checking"},
        {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": str(p)}},
    ]
    tool_result = agent.messages[2]
    assert tool_result["role"] == "tool"
    assert tool_result["tool_call_id"] == "t1"
    assert "needle line" in tool_result["content"]
    assert tool_result["is_error"] is False
    assert agent.messages[3] == {"role": "assistant", "content": "it contains a needle"}
    # second stream call carried the block history and the tool definitions
    assert client.calls[1][1] == registry.definitions()


def test_unparseable_arguments_become_error_result():
    registry = ToolRegistry()
    from core.tools.glob import GlobTool

    registry.register(GlobTool())
    client = FakeLLMClient(
        [
            [ToolCall(id="bad", name="Glob", arguments="{oops")],
            [TextDelta("recovered")],
        ]
    )
    agent = _agent(client, registry)
    assert agent.run("x") == "recovered"
    result = agent.messages[2]
    assert result["is_error"] is True
    assert result["content"].startswith("Error: could not parse tool arguments")
    # the tool_use block still holds a valid (empty) input object
    assert agent.messages[1]["content"][0]["input"] == {}


class _NoArgTool(Tool):
    name = "Ping"
    description = "takes no arguments"
    parameters = {"type": "object", "properties": {}}

    def run(self) -> str:
        return "pong"


def test_empty_arguments_default_to_no_kwargs():
    registry = ToolRegistry()
    registry.register(_NoArgTool())
    client = FakeLLMClient(
        [
            [ToolCall(id="t", name="Ping", arguments="")],  # GLM quirk: empty string
            [TextDelta("done")],
        ]
    )
    agent = _agent(client, registry)
    assert agent.run("ping") == "done"
    assert agent.messages[2]["content"] == "pong"
    assert agent.messages[2]["is_error"] is False


def test_unknown_tool_is_reported_not_raised():
    client = FakeLLMClient(
        [
            [ToolCall(id="t", name="NoSuchTool", arguments="{}")],
            [TextDelta("ok")],
        ]
    )
    agent = _agent(client, ToolRegistry())
    assert agent.run("x") == "ok"
    assert agent.messages[2]["content"] == "Error: unknown tool 'NoSuchTool'"


def test_approval_denial_blocks_write_and_continues(tmp_path):
    registry = ToolRegistry()
    from core.tools.write import WriteTool

    registry.register(WriteTool())
    target = tmp_path / "out.txt"
    client = FakeLLMClient(
        [
            [
                ToolCall(
                    id="t",
                    name="Write",
                    arguments=json.dumps({"file_path": str(target), "content": "x"}),
                )
            ],
            [TextDelta("understood")],
        ]
    )
    agent = _agent(client, registry, approver=lambda tool, args: False)
    assert agent.run("write it") == "understood"
    assert agent.messages[2]["content"] == "[Denied by user]"
    assert agent.messages[2]["is_error"] is True
    assert not target.exists()


def test_approval_grant_runs_tool(tmp_path):
    registry = ToolRegistry()
    from core.tools.write import WriteTool

    registry.register(WriteTool())
    target = tmp_path / "out.txt"
    client = FakeLLMClient(
        [
            [
                ToolCall(
                    id="t",
                    name="Write",
                    arguments=json.dumps({"file_path": str(target), "content": "x"}),
                )
            ],
            [TextDelta("written")],
        ]
    )
    agent = _agent(client, registry, approver=lambda tool, args: True)
    assert agent.run("write it") == "written"
    assert target.read_text() == "x"


def test_interrupt_during_stream_appends_nothing():
    client = FakeLLMClient([KeyboardInterrupt()])
    agent = _agent(client)
    assert agent.run("hello") == "[Response generation was interrupted]"
    assert agent.messages == [{"role": "user", "content": "hello"}]


class _InterruptingTool(Tool):
    name = "Boom"
    description = "raises KeyboardInterrupt while running"
    parameters = {"type": "object", "properties": {}}

    def run(self) -> str:
        raise KeyboardInterrupt


def test_interrupt_during_execution_fills_synthetic_results(tmp_path):
    registry = ToolRegistry()
    from core.tools.read import ReadTool

    registry.register(_InterruptingTool())
    p = tmp_path / "f.txt"
    p.write_text("data\n")
    registry.register(ReadTool())

    client = FakeLLMClient(
        [
            [
                ToolCall(id="t1", name="Boom", arguments="{}"),
                ToolCall(id="t2", name="Read", arguments=json.dumps({"file_path": str(p)})),
            ],
            [TextDelta("never reached")],
        ]
    )
    agent = _agent(client, registry)
    assert agent.run("go") == "[Tool execution was interrupted]"
    # every tool_use got a tool_result: history stays protocol-valid
    results = agent.messages[2:]
    assert [r["tool_call_id"] for r in results] == ["t1", "t2"]
    assert all(r["content"] == "[Interrupted by user before execution]" for r in results)
    assert all(r["is_error"] for r in results)
    assert "data" not in results[1]["content"]  # Read never ran


class _BuggyTool(Tool):
    name = "Buggy"
    description = "raises a plain bug"
    parameters = {"type": "object", "properties": {}}

    def run(self) -> str:
        raise ValueError("boom")


def test_tool_bug_becomes_error_result_and_loop_continues():
    registry = ToolRegistry()
    registry.register(_BuggyTool())
    client = FakeLLMClient(
        [
            [ToolCall(id="t1", name="Buggy", arguments="{}")],
            [TextDelta("noted the failure")],
        ]
    )
    agent = _agent(client, registry)
    assert agent.run("x") == "noted the failure"
    assert agent.messages[2]["content"] == "Error: ValueError: boom"
    assert agent.messages[2]["is_error"] is True


def test_round_limit_stops_loop_with_valid_history(monkeypatch):
    monkeypatch.setattr(Config, "MAX_TOOL_ROUNDS", 3)
    registry = ToolRegistry()
    from core.tools.glob import GlobTool

    registry.register(GlobTool())
    client = FakeLLMClient(
        [],  # every round comes from `repeat`
        repeat=[ToolCall(id="t", name="Glob", arguments=json.dumps({"pattern": "*.zzz"}))],
    )
    agent = _agent(client, registry)
    assert agent.run("loop") == "[Tool round limit reached]"
    assert len(client.calls) == 3
    # every round's tool_use is answered by a tool_result
    assert len(agent.messages) == 1 + 2 * 3


def test_parallel_calls_in_one_round(tmp_path):
    registry = ToolRegistry()
    from core.tools.read import ReadTool
    from core.tools.write import WriteTool

    registry.register(ReadTool())
    registry.register(WriteTool())
    a = tmp_path / "a.txt"
    a.write_text("A\n")
    b = tmp_path / "b.txt"
    b.write_text("B\n")

    client = FakeLLMClient(
        [
            [
                ToolCall(id="t1", name="Read", arguments=json.dumps({"file_path": str(a)})),
                ToolCall(id="t2", name="Read", arguments=json.dumps({"file_path": str(b)})),
            ],
            [TextDelta("both read")],
        ]
    )
    agent = _agent(client, registry)
    assert agent.run("read both") == "both read"
    assert [m["role"] for m in agent.messages] == [
        "user",
        "assistant",
        "tool",
        "tool",
        "assistant",
    ]
    assert [m["tool_call_id"] for m in agent.messages[2:4]] == ["t1", "t2"]


def test_clear_resets_history():
    agent = _agent(FakeLLMClient([[TextDelta("ok")]]))
    agent.run("hello")
    agent.clear()
    assert agent.messages == []


def test_tools_passed_to_client_only_with_registry():
    registry = ToolRegistry()
    from core.tools.glob import GlobTool

    registry.register(GlobTool())
    client = FakeLLMClient([[TextDelta("hi")]])
    agent = _agent(client, registry)
    agent.run("hello")
    assert client.calls[0][1] == registry.definitions()


# ---- parallel batch execution ----


class _JoinTool(Tool):
    """Parallel-safe tool that only finishes when a sibling is also running."""

    name = "Join"
    description = "blocks until a sibling call is also inside run()"
    parameters = {
        "type": "object",
        "properties": {"marker": {"type": "string"}},
        "required": ["marker"],
    }
    parallel_safe = True

    def __init__(self):
        super().__init__()
        self.barrier = threading.Barrier(2, timeout=5)

    def run(self, marker: str) -> str:
        self.barrier.wait()  # BrokenBarrierError if the calls do not overlap
        return f"ran {marker}"


def test_parallel_safe_calls_run_concurrently():
    registry = ToolRegistry()
    registry.register(_JoinTool())
    client = FakeLLMClient(
        [
            [
                ToolCall(id="t1", name="Join", arguments=json.dumps({"marker": "a"})),
                ToolCall(id="t2", name="Join", arguments=json.dumps({"marker": "b"})),
            ],
            [TextDelta("both overlapped")],
        ]
    )
    agent = _agent(client, registry)
    assert agent.run("go") == "both overlapped"  # a sequential run would time out
    assert [m["content"] for m in agent.messages[2:4]] == ["ran a", "ran b"]
    assert all(m["is_error"] is False for m in agent.messages[2:4])


class _SleepyTool(Tool):
    name = "Sleepy"
    description = "parallel-safe tool that sleeps before answering"
    parameters = {
        "type": "object",
        "properties": {"marker": {"type": "string"}},
        "required": ["marker"],
    }
    parallel_safe = True

    def run(self, marker: str) -> str:
        time.sleep(0.15 if marker == "slow" else 0.0)
        return f"ran {marker}"


def test_parallel_results_keep_call_order():
    registry = ToolRegistry()
    registry.register(_SleepyTool())
    client = FakeLLMClient(
        [
            [
                ToolCall(id="t1", name="Sleepy", arguments=json.dumps({"marker": "slow"})),
                ToolCall(id="t2", name="Sleepy", arguments=json.dumps({"marker": "fast"})),
            ],
            [TextDelta("ordered")],
        ]
    )
    agent = _agent(client, registry)
    assert agent.run("go") == "ordered"
    # "fast" finishes first, but results stay in the order the model called them
    assert [m["tool_call_id"] for m in agent.messages[2:4]] == ["t1", "t2"]
    assert [m["content"] for m in agent.messages[2:4]] == ["ran slow", "ran fast"]


def test_sequential_tools_run_in_call_order(tmp_path):
    """Non-parallel-safe calls keep strict ordering: Write lands before Read."""
    registry = ToolRegistry()
    from core.tools.read import ReadTool
    from core.tools.write import WriteTool

    registry.register(WriteTool())
    registry.register(ReadTool())
    target = tmp_path / "ordered.txt"
    client = FakeLLMClient(
        [
            [
                ToolCall(
                    id="t1",
                    name="Write",
                    arguments=json.dumps({"file_path": str(target), "content": "written first"}),
                ),
                ToolCall(id="t2", name="Read", arguments=json.dumps({"file_path": str(target)})),
            ],
            [TextDelta("read what was written")],
        ]
    )
    agent = _agent(client, registry)
    assert agent.run("write then read") == "read what was written"
    assert "written first" in agent.messages[3]["content"]


def test_interrupt_during_parallel_batch_fills_synthetic_results():
    registry = ToolRegistry()
    registry.register(_SleepyTool())
    registry.register(_InterruptingTool())
    client = FakeLLMClient(
        [
            [
                ToolCall(id="t1", name="Sleepy", arguments=json.dumps({"marker": "slow"})),
                ToolCall(id="t2", name="Boom", arguments="{}"),
            ],
            [TextDelta("never reached")],
        ]
    )
    agent = _agent(client, registry)
    assert agent.run("go") == "[Tool execution was interrupted]"
    # the still-running parallel call and the never-started one both get
    # synthetic results: every tool_use stays answered
    results = agent.messages[2:4]
    assert [r["tool_call_id"] for r in results] == ["t1", "t2"]
    assert all(r["content"] == "[Interrupted by user before execution]" for r in results)
    assert all(r["is_error"] for r in results)


def test_tool_bug_does_not_stop_sibling_calls():
    """A crashing tool ruins its own result; the rest of the batch still runs."""
    registry = ToolRegistry()
    registry.register(_BuggyTool())
    registry.register(_NoArgTool())
    client = FakeLLMClient(
        [
            [
                ToolCall(id="t1", name="Buggy", arguments="{}"),
                ToolCall(id="t2", name="Ping", arguments="{}"),
            ],
            [TextDelta("recovered")],
        ]
    )
    agent = _agent(client, registry)
    assert agent.run("x") == "recovered"
    assert agent.messages[2]["content"] == "Error: ValueError: boom"
    assert agent.messages[2]["is_error"] is True
    assert agent.messages[3]["content"] == "pong"
    assert agent.messages[3]["is_error"] is False
