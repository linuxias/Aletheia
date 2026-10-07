import pytest

from core.sandbox.base import CommandResult, SandboxError
from core.sandbox.local import LocalBackend


def test_exit_code_is_data_not_error():
    result = LocalBackend().run_command("exit 3", timeout=10)
    assert isinstance(result, CommandResult)
    assert result.exit_code == 3


def test_stdout_and_stderr_are_separate():
    result = LocalBackend().run_command("echo out; echo err 1>&2", timeout=10)
    assert "out" in result.stdout
    assert "err" in result.stderr


def test_timeout_raises_with_partial_detail():
    with pytest.raises(SandboxError) as excinfo:
        LocalBackend().run_command("echo early; sleep 5", timeout=1)
    assert "timed out after 1s" in str(excinfo.value)
    assert "early" in excinfo.value.detail


def test_command_not_found_is_a_normal_result():
    result = LocalBackend().run_command("aletheia_no_such_cmd", timeout=10)
    assert result.exit_code != 0
    assert "not found" in result.stderr
