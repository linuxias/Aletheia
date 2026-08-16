"""
LLM protocol registry and factory.

The protocol is selected at runtime via the LLM_PROTOCOL environment
variable (.env): anthropic (default) / openai-chat / openai-responses

Adapter modules are imported lazily inside create_client so that only the
selected protocol's SDK (anthropic / openai) is loaded at startup.
"""
import importlib
from typing import Optional

from core.llm.base import LLMClient

# protocol name -> (module path, adapter class name)
_PROTOCOLS = {
    "anthropic": ("core.llm.anthropic_client", "AnthropicMessagesClient"),
    "openai-chat": ("core.llm.openai_chat_client", "OpenAIChatClient"),
    "openai-responses": ("core.llm.openai_responses_client", "OpenAIResponsesClient"),
}


def create_client(protocol: str, api_key: str, base_url: Optional[str] = None) -> LLMClient:
    """Create an LLMClient instance matching the protocol name."""
    name = protocol.strip().lower()
    if name not in _PROTOCOLS:
        raise ValueError(
            f"Unknown LLM_PROTOCOL: {protocol!r} "
            f"(valid values: {', '.join(sorted(_PROTOCOLS))})"
        )
    module_path, class_name = _PROTOCOLS[name]
    adapter = getattr(importlib.import_module(module_path), class_name)
    return adapter(api_key=api_key, base_url=base_url)
