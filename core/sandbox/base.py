"""
Sandbox contract: where the Bash tool's shell commands run.

A backend wraps each command in an isolated environment (or runs it
directly, for the default local backend). The Bash tool keeps everything
the model sees — argument handling, output formatting, clipping, and the
"Error: ..." string contract — so backends only own the mechanics of
running one command. Backends raise SandboxError for expected failures;
callers render it as an "Error: ..." string.
"""
from typing import NamedTuple, Protocol


class CommandResult(NamedTuple):
    stdout: str
    stderr: str
    # A non-zero exit code is a normal result, never an exception.
    exit_code: int


class SandboxError(Exception):
    """Expected sandbox failure; callers render it as 'Error: ...'.

    `detail` carries best-effort extra output, e.g. partial stdout and
    stderr captured before a timeout.
    """

    def __init__(self, message: str, detail: str = "") -> None:
        super().__init__(message)
        self.detail = detail


class Sandbox(Protocol):
    def run_command(self, command: str, timeout: float) -> CommandResult: ...
