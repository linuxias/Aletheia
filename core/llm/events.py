"""Protocol-neutral stream events yielded by LLMClient adapters."""
from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON string; parsing it is the caller's job


StreamEvent = Union[TextDelta, ToolCall]
