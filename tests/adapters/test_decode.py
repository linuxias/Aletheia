from types import SimpleNamespace as SN

from core.llm.anthropic_client import decode as decode_anthropic
from core.llm.events import TextDelta, ToolCall
from core.llm.openai_chat_client import decode as decode_chat
from core.llm.openai_responses_client import decode as decode_responses


def _events(decode_fn, raw):
    return list(decode_fn(iter(raw)))


# ---------- anthropic ----------

def _a_text(text):
    return SN(type="content_block_delta", index=0, delta=SN(type="text_delta", text=text))


def _a_start(index, id, name):
    return SN(
        type="content_block_start",
        index=index,
        content_block=SN(type="tool_use", id=id, name=name),
    )


def _a_json(index, fragment):
    return SN(
        type="content_block_delta",
        index=index,
        delta=SN(type="input_json_delta", partial_json=fragment),
    )


def _a_stop(index):
    return SN(type="content_block_stop", index=index)


def test_anthropic_text_and_split_json_tool_call():
    out = _events(
        decode_anthropic,
        [
            SN(  # text block start: not a tool call, ignored
                type="content_block_start",
                index=0,
                content_block=SN(type="text", text=""),
            ),
            _a_text("Let me check. "),
            _a_start(1, "tu1", "Read"),
            _a_json(1, '{"file_'),
            _a_json(1, 'path": "x"}'),
            _a_stop(0),
            _a_stop(1),
        ],
    )
    assert out == [
        TextDelta("Let me check. "),
        ToolCall(id="tu1", name="Read", arguments='{"file_path": "x"}'),
    ]


def test_anthropic_tool_call_without_arg_deltas():
    out = _events(decode_anthropic, [_a_start(0, "tu2", "Glob"), _a_stop(0)])
    assert out == [ToolCall(id="tu2", name="Glob", arguments="")]


def test_anthropic_parallel_tool_calls_in_order():
    out = _events(
        decode_anthropic,
        [
            _a_start(0, "a", "Read"),
            _a_start(1, "b", "Grep"),
            _a_json(1, "{}"),
            _a_stop(1),
            _a_stop(0),
        ],
    )
    assert [c.id for c in out] == ["b", "a"]  # emitted at their stop events


# ---------- openai chat ----------

def _chunk(content=None, tool_calls=None):
    return SN(choices=[SN(delta=SN(content=content, tool_calls=tool_calls))])


def _tc(index, id=None, name=None, args=None):
    function = SN(name=name, arguments=args) if (name is not None or args is not None) else None
    return SN(index=index, id=id, function=function)


def test_chat_accumulates_fragments_and_skips_usage_chunks():
    out = _events(
        decode_chat,
        [
            SN(choices=[]),  # usage chunk
            _chunk(content="Looking"),
            _chunk(tool_calls=[_tc(0, id="c1", name="Re", args='{"a')]),
            _chunk(tool_calls=[_tc(0, name="ad", args=': 1}')]),
            _chunk(tool_calls=[_tc(1, id="c2", name="Grep", args="{}")]),
        ],
    )
    assert out == [
        TextDelta("Looking"),
        ToolCall(id="c1", name="Read", arguments='{"a: 1}'),
        ToolCall(id="c2", name="Grep", arguments="{}"),
    ]


def test_chat_synthesizes_missing_id():
    out = _events(decode_chat, [_chunk(tool_calls=[_tc(0, name="Bash", args="{}")])])
    assert out == [ToolCall(id="call_0", name="Bash", arguments="{}")]


def test_chat_flush_order_by_index():
    out = _events(
        decode_chat,
        [
            _chunk(tool_calls=[_tc(1, id="late", name="B", args="{}")]),
            _chunk(tool_calls=[_tc(0, id="early", name="A", args="{}")]),
        ],
    )
    assert [c.id for c in out] == ["early", "late"]


# ---------- openai responses ----------

def _r_added(output_index, item_id, call_id, name):
    return SN(
        type="response.output_item.added",
        output_index=output_index,
        item=SN(type="function_call", id=item_id, call_id=call_id, name=name),
    )


def _r_delta(fragment, item_id=None, output_index=None):
    return SN(
        type="response.function_call_arguments.delta",
        item_id=item_id,
        output_index=output_index,
        delta=fragment,
    )


def _r_done(output_index, item_id, call_id, name, arguments):
    return SN(
        type="response.output_item.done",
        output_index=output_index,
        item=SN(type="function_call", id=item_id, call_id=call_id, name=name, arguments=arguments),
    )


def test_responses_tool_call_uses_call_id_and_done_arguments():
    out = _events(
        decode_responses,
        [
            SN(type="response.output_text.delta", delta="Working"),
            _r_added(2, "item_9", "call_9", "Read"),
            _r_delta('{"a', item_id="item_9", output_index=2),
            _r_delta(": 1}", item_id="item_9", output_index=2),
            _r_done(2, "item_9", "call_9", "Read", '{"a": 1}'),
        ],
    )
    assert out == [
        TextDelta("Working"),
        ToolCall(id="call_9", name="Read", arguments='{"a": 1}'),
    ]


def test_responses_resolves_deltas_without_item_id_by_output_index():
    out = _events(
        decode_responses,
        [
            _r_added(0, "item_1", "call_1", "Bash"),
            _r_delta('{"c', item_id=None, output_index=0),
            _r_delta('ommand": "ls"}', item_id=None, output_index=0),
            _r_done(0, "item_1", "call_1", "Bash", '{"command": "ls"}'),
        ],
    )
    assert out[-1].arguments == '{"command": "ls"}'


def test_responses_ignores_non_function_items():
    out = _events(
        decode_responses,
        [
            SN(
                type="response.output_item.added",
                output_index=0,
                item=SN(type="message", id="m1"),
            ),
        ],
    )
    assert out == []
