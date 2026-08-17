"""
End-to-end tool tests against the real GLM API.

The model receives the full tool list via stream() (registry.definitions())
and must pick the right tool for each natural-language task — prompts never
mention tool names, so a pass proves the model selects and invokes each
tool from context. Write/Edit/Bash go through the approval gate with an
auto-allowing approver, exercising the same code path as the interactive
y/N prompt.

Skipped unless ALETHEIA_E2E=1 and LLM_KEY is configured:

    ALETHEIA_E2E=1 uv run pytest tests/test_e2e_tools.py -v -s
    ALETHEIA_E2E=1 LLM_PROTOCOL=openai-chat uv run pytest tests/test_e2e_tools.py
"""
import os

import pytest

from config import Config
from core.agent import Agent
from core.llm import create_client
from core.tools import FileState, ToolRegistry, register_builtins

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.environ.get("ALETHEIA_E2E") != "1" or not Config.API_KEY,
        reason="set ALETHEIA_E2E=1 (and configure LLM_KEY) to run real-API tests",
    ),
]

SYSTEM = (
    "You are a tool-calling test agent. Complete each task using the "
    "available tools. Prefer the dedicated file tools over the shell."
)


def _tool_calls(agent):
    """(tool name, input) for every tool_use block in the history."""
    return [
        (b["name"], b["input"])
        for m in agent.messages
        if isinstance(m.get("content"), list)
        for b in m["content"]
        if b.get("type") == "tool_use"
    ]


def _used(agent):
    return [name for name, _ in _tool_calls(agent)]


@pytest.fixture()
def agent():
    registry = ToolRegistry()
    register_builtins(registry, FileState())
    return Agent(
        system_prompt=SYSTEM,
        client=create_client(Config.PROTOCOL, Config.API_KEY, Config.BASE_URL),
        tools=registry,
        approver=lambda tool, args: True,
    )


def test_model_selects_and_runs_each_tool(agent, tmp_path):
    print(f"protocol: {Config.PROTOCOL}")
    # --- Read ---
    f = tmp_path / "note.txt"
    f.write_text("aletheia-secret-line-7301\nsecond line\n")
    out = agent.run(f"파일 {f}의 첫 번째 줄에 뭐라고 적혀 있나요?")
    assert "Read" in _used(agent), f"model chose {_used(agent)}"
    assert "aletheia-secret-line-7301" in out

    # --- Glob ---
    (tmp_path / "alpha.py").write_text("x = 1\n")
    (tmp_path / "beta.txt").write_text("y = 2\nneedle-9417 here\n")
    out = agent.run(f"{tmp_path} 안에서 확장자가 .py인 파일을 모두 찾아줘")
    assert "Glob" in _used(agent), f"model chose {_used(agent)}"
    assert "alpha.py" in out

    # --- Grep ---
    out = agent.run(f"'needle-9417' 문자열이 {tmp_path} 안 어느 파일에 있는지 찾아줘")
    assert "Grep" in _used(agent), f"model chose {_used(agent)}"
    assert "beta.txt" in out

    # --- Write ---
    target = tmp_path / "created" / "hello.md"
    out = agent.run(f"{target} 경로에 'hello aletheia'라는 내용만 담긴 파일을 만들어줘")
    assert "Write" in _used(agent), f"model chose {_used(agent)}"
    assert target.read_text().strip() == "hello aletheia"

    # --- Edit ---
    out = agent.run(
        f"{target} 파일에서 'aletheia'를 'world'로 바꿔줘. 파일 전체를 다시 쓰지 말고 "
        "해당 부분만 교체해."
    )
    assert "Edit" in _used(agent), f"model chose {_used(agent)}"
    assert target.read_text().strip() == "hello world"

    # --- Bash ---
    out = agent.run("쉘에서 echo e2e-bash-ok-5150 명령의 출력을 그대로 보여줘")
    assert "Bash" in _used(agent), f"model chose {_used(agent)}"
    assert "e2e-bash-ok-5150" in out

    # Every tool_use in the session is answered by exactly one tool_result.
    used_ids = [b["id"] for m in agent.messages
                if isinstance(m.get("content"), list)
                for b in m["content"] if b.get("type") == "tool_use"]
    result_ids = [m["tool_call_id"] for m in agent.messages if m["role"] == "tool"]
    assert len(used_ids) == len(result_ids)
    assert set(used_ids) == set(result_ids)
    print("tools used in order:", _used(agent))
