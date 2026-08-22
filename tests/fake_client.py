"""Injectable LLMClient for headless TUI tests."""
import time
from typing import Iterator, List, Optional, Sequence

from core.llm.base import LLMClient
from core.llm.events import StreamEvent, TextDelta, ToolCall


class FakeStreamClient(LLMClient):
    """Injectable LLMClient: yields canned chunks with a delay; optionally raises."""

    def __init__(
        self,
        chunks: Sequence[str] = (),
        delay: float = 0.0,
        error: Optional[Exception] = None,
        tool_round: Sequence[ToolCall] = (),
    ) -> None:
        # No super().__init__(): there is no SDK client behind this fake.
        self._chunks = list(chunks)
        self._delay = delay
        self._error = error
        # Yielded by the first stream() call instead of chunks, so a single
        # fake can script a tool round followed by the final text round.
        self._tool_round = list(tool_round)
        self._first_stream = True

    def _new_sdk_client(self, api_key: str, base_url: str) -> None:
        return None  # never used by stream()

    def stream(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        messages: List[dict],
        tools: Optional[List[dict]] = None,
    ) -> Iterator[TextDelta]:
        if self._error is not None:
            raise self._error
        if self._first_stream and self._tool_round:
            self._first_stream = False
            events: List[StreamEvent] = list(self._tool_round)
        else:
            self._first_stream = False
            events = [TextDelta(chunk) for chunk in self._chunks]
        for event in events:
            time.sleep(self._delay)
            yield event
