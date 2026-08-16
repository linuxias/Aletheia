"""
Core Agent Loop (streaming + terminal UI integration).

- Streams responses in real time through the protocol-agnostic LLMClient interface.
- Handles Ctrl+C during generation so the history structure stays intact
  and the conversation can continue after an interruption.
"""
from typing import List, Optional

from config import Config
from core.llm import LLMClient, create_client


class Agent:
    def __init__(
        self,
        system_prompt: str,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        label: str = "agent",
        ui=None,
        client: Optional[LLMClient] = None,
    ):
        # Use the injected client, or select one via environment (LLM_PROTOCOL).
        self.client = client or create_client(Config.PROTOCOL, Config.API_KEY, Config.BASE_URL)
        self.system_prompt = system_prompt
        self.model = model or Config.MODEL
        self.max_tokens = max_tokens or Config.MAX_TOKENS
        self.label = label
        self.ui = ui or _NullUI()
        self.messages: List[dict] = []

    def clear(self):
        """Reset the conversation history."""
        self.messages = []

    def run(self, user_input: str) -> str:
        """Accept user input, stream the response text, and return it."""
        self.messages.append({"role": "user", "content": user_input})

        final_text = self._stream_one_response()
        if final_text is None:
            # Generation was interrupted (the assistant message has not been
            # added to history yet, so the conversation structure stays intact)
            return "[Response generation was interrupted]"

        if final_text:
            # Empty responses (e.g. thinking consumed all max_tokens) are
            # not added to history.
            self.messages.append({"role": "assistant", "content": final_text})
        return final_text

    def _stream_one_response(self) -> Optional[str]:
        self.ui.start_turn(self.label)
        try:
            parts: List[str] = []
            for delta in self.client.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self.system_prompt,
                messages=self.messages,
            ):
                self.ui.text_delta(self.label, delta)
                parts.append(delta)
            self.ui.end_turn(self.label)
            return "".join(parts)
        except KeyboardInterrupt:
            self.ui.interrupted(self.label)
            return None


class _NullUI:
    """No-op UI for using Agent programmatically without a ui injection (tests etc.)."""

    def start_turn(self, label):
        pass

    def text_delta(self, label, text):
        pass

    def end_turn(self, label):
        pass

    def interrupted(self, label):
        pass
