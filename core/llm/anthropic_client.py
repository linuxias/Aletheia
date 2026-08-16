"""
Anthropic Messages protocol adapter.
"""
from typing import Iterator, List

import anthropic

from core.llm.base import LLMClient


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
    ) -> Iterator[str]:
        with self._client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        ) as stream:
            for event in stream:
                if event.type == "content_block_delta" and event.delta.type == "text_delta":
                    yield event.delta.text
