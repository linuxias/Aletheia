"""
LLM connection abstraction.

Protocol adapters (Anthropic Messages / OpenAI Chat Completions / OpenAI
Responses) implement this interface. The Agent depends only on this
interface, so switching protocols is just a matter of passing a different
object from core.llm.create_client.
"""
from abc import ABC, abstractmethod
from typing import ClassVar, Iterator, List, Optional


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
    ) -> Iterator[str]:
        """Yield the response text as deltas.

        - messages is a list of {"role": "user"|"assistant", "content": str}.
        - Skip reasoning/thinking deltas; yield final text only.
        - Do not catch KeyboardInterrupt (interruption is the Agent's job).
          Keep the yield inside the SDK stream's with block so the
          connection is closed deterministically on interruption.
        """
