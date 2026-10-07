"""
Bubblewrap sandbox backend: each command runs inside a bwrap mount and
network namespace — the OS-level approach Claude Code and Codex use for
shell commands. Writes are limited to the working directory and an
ephemeral /tmp; the network is unshared; the environment is scrubbed to
a passthrough allowlist so API keys and agent configuration never reach
the command.
"""
import os
import subprocess
from typing import Callable, List

from core.sandbox.base import CommandResult, SandboxError
from core.sandbox.local import _partial

# Environment variables carried into the sandbox; everything else is
# dropped by --clearenv and only these are re-set.
_PASSTHROUGH_ENV = ("PATH", "HOME", "LANG", "TERM")


class BwrapBackend:
    def __init__(
        self, run: Callable[..., subprocess.CompletedProcess] = subprocess.run
    ) -> None:
        self._run = run

    def run_command(self, command: str, timeout: float) -> CommandResult:
        argv = _argv(command)
        try:
            proc = self._run(argv, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise SandboxError(
                f"command timed out after {timeout}s", _partial(e)
            ) from None
        except OSError as e:
            raise SandboxError(str(e)) from None
        return CommandResult(
            stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode
        )


def _argv(command: str) -> List[str]:
    cwd = os.getcwd()
    argv = [
        "bwrap",
        "--ro-bind", "/", "/",
        "--bind", cwd, cwd,
        "--tmpfs", "/tmp",
        "--dev", "/dev",
        "--proc", "/proc",
        "--unshare-net",
        "--die-with-parent",
        "--clearenv",
    ]
    for name in _PASSTHROUGH_ENV:
        if name in os.environ:
            argv += ["--setenv", name, os.environ[name]]
    # The command is a single argv element: no host shell ever parses it.
    argv += ["sh", "-c", command]
    return argv
