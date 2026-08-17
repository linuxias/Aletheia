"""
LLM connection abstraction.

Protocol adapters (Anthropic Messages / OpenAI Chat Completions / OpenAI
Responses) implement this interface. The Agent depends only on this
interface, so switching protocols is just a matter of passing a different
object from core.llm.create_client.
"""
from abc import ABC, abstractmethod
from typing import ClassVar, Iterator, List, Optional

from core.llm.events import StreamEvent


class LLMClient(ABC):
    """Protocol-independent LLM connection interface.

    The shared constructor stores the underlying SDK client built by
    _new_sdk_client, so subclasses only define their protocol specifics
    (registry key, default endpoint, SDK construction, stream decoding).
    """

    # Registry key ("anthropic" / "openai-chat" / "openai-responses")
    protocol_name: ClassVar[str]

    # Per-protocol GLM Coding Plan endpoint
    DEFAULT_BASE_URL: ClassVar[str]

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        self._client = self._new_sdk_client(api_key, base_url or self.DEFAULT_BASE_URL)

    @abstractmethod
    def _new_sdk_client(self, api_key: str, base_url: str):
        """Create the underlying SDK client bound to the effective base_url."""

    @abstractmethod
    def stream(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        messages: List[dict],
        tools: Optional[List[dict]] = None,
    ) -> Iterator[StreamEvent]:
        """Yield TextDelta for each visible text fragment and exactly one
        ToolCall per completed tool invocation, in order.

        - tools is a list of neutral definitions
          {"name": str, "description": str, "parameters": <JSON Schema dict>}
          or None when the caller wants plain text-only generation. Adapters
          must omit the wire tools parameter entirely when tools is None or
          empty.
        - messages is the neutral history: {"role": "user"|"assistant",
          "content": str}, assistant entries whose content is a list of
          {"type": "text", "text"} / {"type": "tool_use", "id", "name",
          "input"} blocks, and {"role": "tool", "tool_call_id", "content",
          "is_error"} result entries. Adapters translate to their wire
          format and must preserve ordering (Anthropic requires every
          tool_use to be answered by a tool_result in the immediately
          following user message).
        - ToolCall.arguments is the raw accumulated JSON string; parsing it
          is the caller's job. Emit ToolCall only after the arguments are
          complete.
        - Skip reasoning/thinking deltas; yield final text only.
        - Do not catch KeyboardInterrupt (interruption is the Agent's job).
          Keep the yield inside the SDK stream's with block so the
          connection is closed deterministically on interruption.
        """
