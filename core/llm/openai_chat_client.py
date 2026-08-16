"""
OpenAI Chat Completions protocol adapter.
"""
from typing import Iterator, List

import openai

from core.llm.base import LLMClient


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
    ) -> Iterator[str]:
        with self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            stream=True,
            messages=[{"role": "system", "content": system}, *messages],
        ) as stream:
            for chunk in stream:
                if not chunk.choices:  # chunks with empty choices (e.g. usage)
                    continue
                delta = chunk.choices[0].delta
                if delta.content:  # None chunks are reasoning/role -> skipped
                    yield delta.content
