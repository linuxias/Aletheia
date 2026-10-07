"""Local sandbox backend: commands run directly on the host, as before."""
import subprocess

from core.sandbox.base import CommandResult, SandboxError


class LocalBackend:
    def run_command(self, command: str, timeout: float) -> CommandResult:
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise SandboxError(
                f"command timed out after {timeout}s", _partial(e)
            ) from None
        except OSError as e:
            raise SandboxError(str(e)) from None
        return CommandResult(
            stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode
        )


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


# Stateless, so one shared instance serves every BashTool constructed
# without an explicit sandbox.
default_sandbox = LocalBackend()
