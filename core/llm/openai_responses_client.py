"""
OpenAI Responses protocol adapter.

Translation between the neutral message IR and the Responses API input
items, plus streaming decode of text and function_call argument events.
The module-level helpers are pure so they can be unit-tested without
network access.
"""
import json
from typing import Dict, Iterator, List, Optional

import openai

from core.llm.base import LLMClient
from core.llm.events import StreamEvent, TextDelta, ToolCall


def to_responses_tools(tools: List[dict]) -> List[dict]:
    # Flat shape: no nested "function" key, unlike chat completions.
    return [
        {
            "type": "function",
            "name": t["name"],
            "description": t["description"],
            "parameters": t["parameters"],
        }
        for t in tools
    ]


def to_responses_input(messages: List[dict]) -> List[dict]:
    """Neutral IR -> Responses API input items.

    Returns a flat list mixing plain message dicts and function_call /
    function_call_output items (both shapes are accepted at the top level
    of input). is_error has no wire equivalent here; the error-ness stays
    visible through the result content itself.
    """
    items: List[dict] = []
    for msg in messages:
        if msg["role"] == "tool":
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": msg["tool_call_id"],
                    "output": msg["content"],
                }
            )
            continue
        content = msg["content"]
        if isinstance(content, str):
            items.append({"role": msg["role"], "content": content})
            continue
        text = "".join(b["text"] for b in content if b["type"] == "text")
        if text:
            items.append({"role": "assistant", "content": text})
        for b in content:
            if b["type"] == "tool_use":
                items.append(
                    {
                        "type": "function_call",
                        "call_id": b["id"],
                        "name": b["name"],
                        "arguments": json.dumps(b["input"], ensure_ascii=False),
                    }
                )
    return items


def decode(events) -> Iterator[StreamEvent]:
    """Responses streaming events -> neutral StreamEvents.

    Compares against string literals (SDK class names have been renamed
    across versions). Argument deltas are keyed by item_id, falling back
    to output_index for servers that omit item_id; the ToolCall id is the
    item's call_id — function_call_output references call_id, not the
    item id.
    """
    pending: Dict[str, dict] = {}  # item_id -> {call_id, name, args}
    by_index: Dict[int, str] = {}  # output_index -> item_id
    for event in events:
        etype = event.type
        if etype == "response.output_text.delta":
            yield TextDelta(event.delta)
        elif etype == "response.output_item.added":
            item = event.item
            if getattr(item, "type", None) == "function_call":
                item_id = item.id or f"_index_{event.output_index}"
                pending[item_id] = {
                    "call_id": item.call_id,
                    "name": item.name,
                    "args": "",
                }
                by_index[event.output_index] = item_id
        elif etype in (
            "response.function_call_arguments.delta",
            "response.function_call_arguments.done",
        ):
            item_id = getattr(event, "item_id", None) or by_index.get(
                getattr(event, "output_index", None)
            )
            slot = pending.get(item_id) if item_id else None
            if slot is not None:
                if etype.endswith(".done"):
                    slot["args"] = event.arguments  # authoritative full value
                else:
                    slot["args"] += event.delta
        elif etype == "response.output_item.done":
            item = event.item
            if getattr(item, "type", None) == "function_call":
                item_id = getattr(item, "id", None) or by_index.get(event.output_index)
                pending.pop(item_id, None)
                yield ToolCall(id=item.call_id, name=item.name, arguments=item.arguments)


class OpenAIResponsesClient(LLMClient):
    protocol_name = "openai-responses"
    DEFAULT_BASE_URL = "https://api.z.ai/api/v1"

    def _new_sdk_client(self, api_key: str, base_url: str):
        return openai.OpenAI(api_key=api_key, base_url=base_url)

    def stream(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        messages: List[dict],
        tools: Optional[List[dict]] = None,
    ) -> Iterator[StreamEvent]:
        kwargs = dict(
            model=model,
            input=to_responses_input(messages),
            instructions=system,
            max_output_tokens=max_tokens,
            stream=True,
        )
        if tools:
            kwargs["tools"] = to_responses_tools(tools)
        with self._client.responses.create(**kwargs) as stream:
            yield from decode(stream)
