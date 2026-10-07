import subprocess

import pytest

from core.sandbox.base import CommandResult, SandboxError
from core.sandbox.bwrap import BwrapBackend


class _FakeCompleted:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class RecordingRun:
    """Stand-in for subprocess.run that records every invocation."""

    def __init__(self, completed=None):
        self.calls = []
        self._completed = completed or _FakeCompleted()

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        return self._completed


def _setenv_names(argv):
    """Names passed via --setenv, i.e. the environment the command sees."""
    return {
        value
        for i, value in enumerate(argv)
        if i > 0 and argv[i - 1] == "--setenv"
    }


def test_argv_pins_isolation_policy(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    recorder = RecordingRun()
    BwrapBackend(run=recorder).run_command("echo hi", timeout=10)

    argv, kwargs = recorder.calls[0]
    assert argv[0] == "bwrap"
    # Read-only root, writable cwd, ephemeral /tmp.
    assert argv[argv.index("--ro-bind") + 1] == "/"
    cwd = str(tmp_path)
    assert argv[argv.index("--bind") + 1 : argv.index("--bind") + 3] == [cwd, cwd]
    assert argv[argv.index("--tmpfs") + 1] == "/tmp"
    assert "--unshare-net" in argv
    assert "--die-with-parent" in argv
    # The command is a single argv element; no host shell parses it.
    assert argv[-3:] == ["sh", "-c", "echo hi"]
    assert kwargs["timeout"] == 10


def test_env_scrubbed_to_passthrough(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_KEY", "secret")
    monkeypatch.setenv("MY_CUSTOM", "leak-me")
    recorder = RecordingRun()
    BwrapBackend(run=recorder).run_command("true", timeout=5)

    argv = recorder.calls[0][0]
    assert "--clearenv" in argv
    names = _setenv_names(argv)
    assert names <= {"PATH", "HOME", "LANG", "TERM"}
    assert "MY_CUSTOM" not in names


def test_result_is_mapped():
    recorder = RecordingRun(
        _FakeCompleted(stdout="out\n", stderr="err\n", returncode=2)
    )
    result = BwrapBackend(run=recorder).run_command("x", timeout=5)
    assert (result.stdout, result.stderr, result.exit_code) == ("out\n", "err\n", 2)


def test_timeout_raises_sandbox_error_with_partial():
    def raising_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=argv, timeout=5, output=b"early", stderr=None
        )

    with pytest.raises(SandboxError) as excinfo:
        BwrapBackend(run=raising_run).run_command("sleep 9", timeout=5)
    assert "timed out after 5s" in str(excinfo.value)
    assert "early" in excinfo.value.detail


def test_concurrent_run_command_calls(tmp_path, monkeypatch):
    """Task subagents execute tools on threads; the backend must allow it."""
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.chdir(tmp_path)
    recorder = RecordingRun()
    backend = BwrapBackend(run=recorder)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(lambda i: backend.run_command(f"echo {i}", timeout=5), range(8))
        )
    assert len(results) == 8
    assert all(r.exit_code == 0 for r in results)
    assert len(recorder.calls) == 8
