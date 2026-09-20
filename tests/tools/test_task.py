import json
import threading
from typing import Iterator, List

from core.agent import Agent
from core.llm.base import LLMClient
from core.llm.events import TextDelta, ToolCall
from core.tools.base import Tool
from core.tools.registry import ToolRegistry
from core.tools.task import TaskTool, create_task_tool


class _EchoAgent:
    """Duck-typed stand-in for Agent: records the prompt, returns a report."""

    def __init__(self, report: str = "subagent report"):
        self.report = report
        self.prompts: List[str] = []

    def run(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.report


def test_task_returns_subagent_report():
    sub = _EchoAgent("experiment 1 finished: accuracy 0.91")
    tool = TaskTool(lambda description: sub)
    out = tool.run(description="run experiment 1", prompt="train and evaluate")
    assert out == "experiment 1 finished: accuracy 0.91"
    assert sub.prompts == ["train and evaluate"]


def test_task_clips_long_reports():
    tool = TaskTool(lambda description: _EchoAgent("x" * 50_000))
    out = tool.run(description="verbose sub", prompt="p")
    assert len(out) < 50_000
    assert "truncated" in out


def test_task_empty_report_marker():
    tool = TaskTool(lambda description: _EchoAgent(""))
    assert tool.run(description="quiet sub", prompt="p") == "(subagent returned no report)"


def test_task_calls_in_one_batch_run_concurrently():
    """Two Task calls must overlap in time (barrier proves the overlap)."""
    barrier = threading.Barrier(2, timeout=5)

    def run_prompt(prompt: str) -> str:
        barrier.wait()  # times out unless both subagents run at once
        return f"done: {prompt}"

    class _BarrierAgent:
        def run(self, prompt: str) -> str:
            return run_prompt(prompt)

    tool = TaskTool(lambda description: _BarrierAgent())

    results: List[str] = []
    threads = [
        threading.Thread(target=lambda i=i: results.append(tool.run(description=f"d{i}", prompt=f"p{i}")))
        for i in range(2)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == ["done: p0", "done: p1"]


# ---- create_task_tool wiring ----


class _ScriptedClient(LLMClient):
    """LLMClient replays scripted batches and records every stream() call."""

    protocol_name = "fake"
    DEFAULT_BASE_URL = "http://localhost"

    def __init__(self, batches):
        self.batches = list(batches)
        self.calls: List[dict] = []  # {system, messages, tools} per stream()

    def _new_sdk_client(self, api_key: str, base_url: str):
        return None

    def stream(self, *, model, max_tokens, system, messages, tools=None) -> Iterator[TextDelta]:
        self.calls.append(
            {
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": list(messages),
                "tools": tools,
            }
        )
        batch = self.batches.pop(0)
        if isinstance(batch, BaseException):
            raise batch
        yield from batch


class _PingTool(Tool):
    name = "Ping"
    description = "returns its argument"
    parameters = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    def run(self, text: str) -> str:
        return f"pong {text}"


def _task_call(call_id: str, description: str, prompt: str) -> ToolCall:
    return ToolCall(
        id=call_id,
        name="Task",
        arguments=json.dumps({"description": description, "prompt": prompt}),
    )


def test_subagent_isolated_history_and_no_delegation():
    """The spawned subagent sees only its prompt, and its registry has no Task."""
    registry = ToolRegistry()
    registry.register(_PingTool())
    client = _ScriptedClient(
        [
            [_task_call("t1", "probe subagent", "go measure the thing")],  # parent round 1
            [TextDelta("sub measured 42")],  # subagent's only round
            [TextDelta("collected")],  # parent round 2
        ]
    )
    parent = Agent(system_prompt="parent prompt", client=client, tools=registry)
    registry.register(create_task_tool(parent))

    assert parent.run("delegate the measurement") == "collected"

    parent_round, sub_round, _ = client.calls
    # the subagent conversation: fresh history, its own system prompt
    assert sub_round["messages"] == [{"role": "user", "content": "go measure the thing"}]
    assert "subagent" in sub_round["system"].lower()
    # one level deep: the subagent's tool list has no Task tool
    assert [d["name"] for d in sub_round["tools"]] == ["Ping"]
    # the parent's history holds the report as the Task tool result
    tool_result = parent.messages[2]
    assert tool_result["tool_call_id"] == "t1"
    assert tool_result["content"] == "sub measured 42"
    assert tool_result["is_error"] is False
    # the parent itself keeps the Task tool
    assert [d["name"] for d in parent_round["tools"]] == ["Ping", "Task"]


def test_parallel_task_calls_in_one_agent_round():
    """Two Task calls issued together run concurrently and both report back."""
    registry = ToolRegistry()
    registry.register(_PingTool())
    client = _ScriptedClient(
        [
            [
                _task_call("t1", "experiment a", "run experiment a"),
                _task_call("t2", "experiment b", "run experiment b"),
            ],
            [TextDelta("a is done")],  # subagent a
            [TextDelta("b is done")],  # subagent b
            [TextDelta("both collected")],
        ]
    )
    parent = Agent(system_prompt="parent", client=client, tools=registry)
    registry.register(create_task_tool(parent))

    assert parent.run("run both") == "both collected"
    results = parent.messages[2:4]
    assert [r["tool_call_id"] for r in results] == ["t1", "t2"]
    assert [r["content"] for r in results] == ["a is done", "b is done"]
    assert all(r["role"] == "tool" for r in results)


def test_subagent_receives_parent_model_and_max_tokens():
    registry = ToolRegistry()
    parent = Agent(
        system_prompt="p",
        client=_ScriptedClient([]),
        tools=registry,
        model="test-model",
        max_tokens=123,
    )
    task = create_task_tool(parent)

    parent.client.batches = [[TextDelta("reported")]]
    assert task.run(description="check wiring", prompt="do it") == "reported"
    (sub_call,) = parent.client.calls
    assert sub_call["model"] == "test-model"
    assert sub_call["max_tokens"] == 123
