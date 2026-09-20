"""
Tool primitives shared by all built-in tools.

A Tool is a self-describing unit: name + description + JSON Schema for its
arguments, and a run() that returns the result as plain text. Expected
failures (missing file, bad regex, non-zero exit) are returned as
"Error: ..." strings, never raised — the model reads the error and
self-corrects. Tools must never catch KeyboardInterrupt or SystemExit.
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar, Optional, Set

# Tool outputs larger than this are clipped (head + tail) before they
# enter the conversation context.
MAX_OUTPUT_CHARS = 30_000
_HEAD_CHARS = 24_000
_TAIL_CHARS = 6_000


def clip(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    """Shorten text to roughly `limit` chars, keeping the head and tail."""
    if len(text) <= limit:
        return text
    omitted = len(text) - _HEAD_CHARS - _TAIL_CHARS
    return (
        text[:_HEAD_CHARS]
        + f"\n[... {omitted} middle characters truncated ...]\n"
        + text[-_TAIL_CHARS:]
    )


class FileState:
    """Session-scoped set of files Read has loaded, for read-before-write."""

    def __init__(self):
        self.read_files: Set[str] = set()

    def mark_read(self, path: str) -> None:
        self.read_files.add(str(Path(path).resolve()))

    def was_read(self, path: str) -> bool:
        return str(Path(path).resolve()) in self.read_files


class Tool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    # JSON Schema object describing the tool's arguments.
    parameters: ClassVar[dict]
    # Tools that mutate the system require per-call user approval.
    requires_approval: ClassVar[bool] = False
    # Parallel-safe tools may be dispatched concurrently with their sibling
    # calls when the model batches several tool calls into one response.
    # They must not depend on execution order or hold exclusive mutable
    # state; tools that touch the filesystem or the shell stay sequential.
    parallel_safe: ClassVar[bool] = False

    def __init__(self, file_state: Optional[FileState] = None):
        self.file_state = file_state

    @abstractmethod
    def run(self, **kwargs) -> str:
        """Execute and return the result text; errors as 'Error: ...'."""
