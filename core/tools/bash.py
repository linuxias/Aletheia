"""Bash tool: shell command execution with timeout and output clipping."""
import subprocess

from core.tools.base import Tool, clip

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

    def run(self, command: str, timeout: int = DEFAULT_TIMEOUT) -> str:
        seconds = min(max(1, int(timeout)), MAX_TIMEOUT)
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=seconds,
            )
        except subprocess.TimeoutExpired as e:
            return f"Error: command timed out after {seconds}s" + _partial(e)
        except OSError as e:
            return f"Error: {e}"

        sections = []
        if proc.stdout:
            sections.append(proc.stdout.rstrip("\n"))
        if proc.stderr:
            sections.append("--- stderr ---\n" + proc.stderr.rstrip("\n"))
        if proc.returncode != 0:
            sections.append(f"Exit code: {proc.returncode}")
        if not sections:
            return "(no output)"
        return clip("\n".join(sections))


def _partial(e: subprocess.TimeoutExpired) -> str:
    """Best-effort partial output captured before a timeout."""
    parts = []
    for label, chunk in (("stdout", e.stdout), ("stderr", e.stderr)):
        if not chunk:
            continue
        if isinstance(chunk, bytes):
            chunk = chunk.decode("utf-8", errors="replace")
        parts.append(f"\n--- partial {label} ---\n{chunk}")
    return "".join(parts)
