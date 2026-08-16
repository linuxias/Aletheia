"""
OpenAI Responses protocol adapter.
"""
from typing import Iterator, List

import openai

from core.llm.base import LLMClient


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
    ) -> Iterator[str]:
        with self._client.responses.create(
            model=model,
            input=messages,
            instructions=system,
            max_output_tokens=max_tokens,
            stream=True,
        ) as stream:
            for event in stream:
                # Compare against the string literal (SDK class names have
                # been renamed across versions). Reasoning events have a
                # different type and are skipped naturally.
                if event.type == "response.output_text.delta":
                    yield event.delta
