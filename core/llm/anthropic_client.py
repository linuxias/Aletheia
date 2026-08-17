"""
Anthropic Messages protocol adapter.

Translation between the neutral message IR and the Anthropic wire format,
plus streaming decode of text/tool_use content blocks. The module-level
helpers are pure so they can be unit-tested without network access.
"""
from typing import Dict, Iterator, List, Optional

import anthropic

from core.llm.base import LLMClient
from core.llm.events import StreamEvent, TextDelta, ToolCall


def to_anthropic_tools(tools: List[dict]) -> List[dict]:
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["parameters"],
        }
        for t in tools
    ]


def _is_tool_result_message(msg: dict) -> bool:
    return (
        msg["role"] == "user"
        and isinstance(msg.get("content"), list)
        and msg["content"]
        and all(b.get("type") == "tool_result" for b in msg["content"])
    )


def to_anthropic_messages(messages: List[dict]) -> List[dict]:
    """Neutral IR -> Anthropic wire messages.

    Consecutive role:"tool" entries merge into a single user message of
    tool_result blocks: Anthropic requires all parallel results in one
    user message immediately after the assistant tool_use turn. Neutral
    user messages always carry str content, so a user message holding
    tool_result blocks can only be one we built.
    """
    out: List[dict] = []
    for msg in messages:
        if msg["role"] == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": msg["tool_call_id"],
                "content": msg["content"],
            }
            if msg.get("is_error"):
                block["is_error"] = True
            if out and _is_tool_result_message(out[-1]):
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
            continue
        content = msg["content"]
        if isinstance(content, list):
            content = [
                {"type": "text", "text": b["text"]}
                if b["type"] == "text"
                else {
                    "type": "tool_use",
                    "id": b["id"],
                    "name": b["name"],
                    "input": b["input"],
                }
                for b in content
            ]
        out.append({"role": msg["role"], "content": content})
    return out


def decode(events) -> Iterator[StreamEvent]:
    """Raw message-stream events -> neutral StreamEvents."""
    pending: Dict[int, dict] = {}  # content block index -> {id, name, json}
    for event in events:
        etype = getattr(event, "type", None)
        if etype == "content_block_start":
            block = event.content_block
            if getattr(block, "type", None) == "tool_use":
                pending[event.index] = {"id": block.id, "name": block.name, "json": ""}
        elif etype == "content_block_delta":
            delta = event.delta
            dtype = getattr(delta, "type", None)
            if dtype == "text_delta":
                yield TextDelta(delta.text)
            elif dtype == "input_json_delta":
                slot = pending.get(event.index)
                if slot is not None:
                    slot["json"] += delta.partial_json
        elif etype == "content_block_stop":
            slot = pending.pop(event.index, None)
            if slot is not None:
                yield ToolCall(id=slot["id"], name=slot["name"], arguments=slot["json"])


class AnthropicMessagesClient(LLMClient):
    protocol_name = "anthropic"
    DEFAULT_BASE_URL = "https://api.z.ai/api/anthropic"

    def _new_sdk_client(self, api_key: str, base_url: str):
        return anthropic.Anthropic(api_key=api_key, base_url=base_url)

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
            max_tokens=max_tokens,
            system=system,
            messages=to_anthropic_messages(messages),
        )
        if tools:
            kwargs["tools"] = to_anthropic_tools(tools)
        with self._client.messages.stream(**kwargs) as stream:
            yield from decode(stream)
