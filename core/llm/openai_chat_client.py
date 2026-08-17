"""
OpenAI Chat Completions protocol adapter.

Translation between the neutral message IR and the chat-completions wire
format, plus streaming decode of text and tool_calls deltas. The
module-level helpers are pure so they can be unit-tested without network
access.
"""
import json
from typing import Dict, Iterator, List, Optional

import openai

from core.llm.base import LLMClient
from core.llm.events import StreamEvent, TextDelta, ToolCall


def to_chat_tools(tools: List[dict]) -> List[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        }
        for t in tools
    ]


def to_chat_messages(system: str, messages: List[dict]) -> List[dict]:
    """Neutral IR -> chat-completions messages.

    Assistant block lists become tool_calls entries; the "content" key is
    omitted when there is no text (strict OpenAI-compatible backends may
    reject null content).
    """
    out: List[dict] = [{"role": "system", "content": system}]
    for msg in messages:
        if msg["role"] == "tool":
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": msg["tool_call_id"],
                    "content": msg["content"],
                }
            )
            continue
        content = msg["content"]
        if isinstance(content, str):
            out.append({"role": msg["role"], "content": content})
            continue
        entry = {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": b["id"],
                    "type": "function",
                    "function": {
                        "name": b["name"],
                        "arguments": json.dumps(b["input"], ensure_ascii=False),
                    },
                }
                for b in content
                if b["type"] == "tool_use"
            ],
        }
        text = "".join(b["text"] for b in content if b["type"] == "text")
        if text:
            entry["content"] = text
        out.append(entry)
    return out


def decode(chunks) -> Iterator[StreamEvent]:
    """Chat-completions stream chunks -> neutral StreamEvents.

    Tool call fragments are accumulated per index (id on the first
    fragment only, name/arguments appended across fragments) and flushed
    in index order once the stream ends — finish_reason is advisory
    across OpenAI-compatible backends, so the full stream is drained.
    """
    slots: Dict[int, dict] = {}  # tool_calls index -> {id, name, args}
    for chunk in chunks:
        if not chunk.choices:  # chunks with empty choices (e.g. usage)
            continue
        delta = chunk.choices[0].delta
        if delta is None:
            continue
        if delta.content:  # None chunks are reasoning/role -> skipped
            yield TextDelta(delta.content)
        for tc in delta.tool_calls or []:
            slot = slots.setdefault(tc.index, {"id": None, "name": "", "args": ""})
            if tc.id:
                slot["id"] = tc.id
            if tc.function is not None:
                if tc.function.name:
                    slot["name"] += tc.function.name
                if tc.function.arguments:
                    slot["args"] += tc.function.arguments
    for index in sorted(slots):
        slot = slots[index]
        yield ToolCall(
            id=slot["id"] or f"call_{index}",
            name=slot["name"],
            arguments=slot["args"],
        )


class OpenAIChatClient(LLMClient):
    protocol_name = "openai-chat"
    DEFAULT_BASE_URL = "https://api.z.ai/api/coding/paas/v4"

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
            max_tokens=max_tokens,
            stream=True,
            messages=to_chat_messages(system, messages),
        )
        if tools:
            kwargs["tools"] = to_chat_tools(tools)
        with self._client.chat.completions.create(**kwargs) as stream:
            yield from decode(stream)
