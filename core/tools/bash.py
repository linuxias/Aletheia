"""Bash tool: shell command execution with timeout and output clipping."""
from typing import Optional

from core.sandbox.base import Sandbox, SandboxError
from core.sandbox.local import default_sandbox
from core.tools.base import FileState, Tool, clip

DEFAULT_TIMEOUT = 120
MAX_TIMEOUT = 600


class BashTool(Tool):
    name = "Bash"
    description = (
        "Run a shell command and return stdout, stderr, and the exit code. "
        "Timeout defaults to 120 seconds (max 600). Non-zero exits are "
        "reported as normal results; timeouts are errors."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command to run"},
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds",
                "default": 120,
            },
        },
        "required": ["command"],
    }
    requires_approval = True

    def __init__(
        self,
        file_state: Optional[FileState] = None,
        sandbox: Optional[Sandbox] = None,
    ):
        super().__init__(file_state)
        self.sandbox = sandbox if sandbox is not None else default_sandbox

    def run(self, command: str, timeout: int = DEFAULT_TIMEOUT) -> str:
        seconds = min(max(1, int(timeout)), MAX_TIMEOUT)
        try:
            result = self.sandbox.run_command(command, seconds)
        except SandboxError as e:
            return f"Error: {e}" + e.detail

        sections = []
        if result.stdout:
            sections.append(result.stdout.rstrip("\n"))
        if result.stderr:
            sections.append("--- stderr ---\n" + result.stderr.rstrip("\n"))
        if result.exit_code != 0:
            sections.append(f"Exit code: {result.exit_code}")
        if not sections:
            return "(no output)"
        return clip("\n".join(sections))
