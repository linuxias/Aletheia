"""Injectable LLMClient for headless TUI tests."""
import time
from typing import Iterator, List, Optional, Sequence

from core.llm.base import LLMClient


class FakeStreamClient(LLMClient):
    """Injectable LLMClient: yields canned chunks with a delay; optionally raises."""

    def __init__(
        self,
        chunks: Sequence[str] = (),
        delay: float = 0.0,
        error: Optional[Exception] = None,
    ) -> None:
        # No super().__init__(): there is no SDK client behind this fake.
        self._chunks = list(chunks)
        self._delay = delay
        self._error = error

    def _new_sdk_client(self, api_key: str, base_url: str) -> None:
        return None  # never used by stream()

    def stream(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        messages: List[dict],
    ) -> Iterator[str]:
        if self._error is not None:
            raise self._error
        for chunk in self._chunks:
            time.sleep(self._delay)
            yield chunk
