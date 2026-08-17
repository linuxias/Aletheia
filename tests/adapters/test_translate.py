import json

from core.llm.anthropic_client import to_anthropic_messages, to_anthropic_tools
from core.llm.openai_chat_client import to_chat_messages, to_chat_tools
from core.llm.openai_responses_client import to_responses_input, to_responses_tools

TOOLS = [{"name": "Read", "description": "read a file", "parameters": {"type": "object"}}]

PLAIN = [
    {"role": "user", "content": "hi"},
    {"role": "assistant", "content": "hello"},
]

BLOCKY = [
    {"role": "user", "content": "list files"},
    {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "checking"},
            {"type": "tool_use", "id": "t1", "name": "Glob", "input": {"pattern": "*.py"}},
            {"type": "tool_use", "id": "t2", "name": "Grep", "input": {"pattern": "x"}},
        ],
    },
    {"role": "tool", "tool_call_id": "t1", "content": "a.py", "is_error": False},
    {"role": "tool", "tool_call_id": "t2", "content": "Error: bad", "is_error": True},
]


# ---------- anthropic ----------

def test_anthropic_plain_history_passes_through():
    assert to_anthropic_messages(PLAIN) == PLAIN


def test_anthropic_blocks_and_merged_tool_results():
    out = to_anthropic_messages(BLOCKY)
    assert out[0] == {"role": "user", "content": "list files"}
    assert out[1]["content"] == [
        {"type": "text", "text": "checking"},
        {"type": "tool_use", "id": "t1", "name": "Glob", "input": {"pattern": "*.py"}},
        {"type": "tool_use", "id": "t2", "name": "Grep", "input": {"pattern": "x"}},
    ]
    # both results in ONE user message, in call order
    assert out[2] == {
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "a.py"},
            {
                "type": "tool_result",
                "tool_use_id": "t2",
                "content": "Error: bad",
                "is_error": True,
            },
        ],
    }
    assert len(out) == 3


def test_anthropic_tools_use_input_schema():
    assert to_anthropic_tools(TOOLS) == [
        {
            "name": "Read",
            "description": "read a file",
            "input_schema": {"type": "object"},
        }
    ]


# ---------- openai chat ----------

def test_chat_prepends_system():
    out = to_chat_messages("be brief", PLAIN)
    assert out[0] == {"role": "system", "content": "be brief"}
    assert out[1:] == PLAIN


def test_chat_blocks_to_tool_calls():
    out = to_chat_messages("s", BLOCKY)
    assistant = out[2]
    assert assistant["role"] == "assistant"
    assert assistant["content"] == "checking"
    assert [tc["id"] for tc in assistant["tool_calls"]] == ["t1", "t2"]
    assert assistant["tool_calls"][0]["function"]["name"] == "Glob"
    assert json.loads(assistant["tool_calls"][0]["function"]["arguments"]) == {
        "pattern": "*.py"
    }
    assert out[3] == {"role": "tool", "tool_call_id": "t1", "content": "a.py"}


def test_chat_omits_content_key_without_text():
    blocky = [
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "t1", "name": "Glob", "input": {}}],
        }
    ]
    assistant = to_chat_messages("s", blocky)[1]
    assert "content" not in assistant


def test_chat_tools_are_nested():
    assert to_chat_tools(TOOLS) == [
        {
            "type": "function",
            "function": {
                "name": "Read",
                "description": "read a file",
                "parameters": {"type": "object"},
            },
        }
    ]


# ---------- openai responses ----------

def test_responses_blocks_to_function_call_items():
    out = to_responses_input(BLOCKY)
    assert out[0] == {"role": "user", "content": "list files"}
    assert out[1] == {"role": "assistant", "content": "checking"}
    assert out[2] == {
        "type": "function_call",
        "call_id": "t1",
        "name": "Glob",
        "arguments": json.dumps({"pattern": "*.py"}, ensure_ascii=False),
    }
    assert out[3] == {
        "type": "function_call",
        "call_id": "t2",
        "name": "Grep",
        "arguments": json.dumps({"pattern": "x"}, ensure_ascii=False),
    }
    assert out[4] == {"type": "function_call_output", "call_id": "t1", "output": "a.py"}
    assert out[5] == {"type": "function_call_output", "call_id": "t2", "output": "Error: bad"}


def test_responses_plain_history():
    assert to_responses_input(PLAIN) == PLAIN


def test_responses_tools_are_flat():
    assert to_responses_tools(TOOLS) == [
        {
            "type": "function",
            "name": "Read",
            "description": "read a file",
            "parameters": {"type": "object"},
        }
    ]
