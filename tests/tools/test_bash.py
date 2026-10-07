from core.tools.bash import BashTool
from core.tools.registry import ToolRegistry


class RecordingSandbox:
    """Fake sandbox that records calls and replays a fixed result."""

    def __init__(self, result=None, error=None):
        from core.sandbox.base import CommandResult

        self.calls = []
        self.result = result or CommandResult(stdout="", stderr="", exit_code=0)
        self.error = error

    def run_command(self, command, timeout):
        self.calls.append((command, timeout))
        if self.error is not None:
            raise self.error
        return self.result


def test_stdout_roundtrip():
    assert BashTool().run(command="echo hello") == "hello"


def test_stderr_section():
    out = BashTool().run(command="echo oops 1>&2")
    assert "--- stderr ---" in out
    assert "oops" in out


def test_stdout_and_stderr_combined():
    out = BashTool().run(command="echo out; echo err 1>&2")
    assert "out" in out and "err" in out


def test_nonzero_exit_is_normal_result():
    registry = ToolRegistry()
    registry.register(BashTool())
    output, is_error = registry.execute("Bash", {"command": "exit 3"})
    assert not is_error
    assert "Exit code: 3" in output


def test_timeout_is_error():
    out = BashTool().run(command="sleep 5", timeout=1)
    assert out.startswith("Error: command timed out after 1s")


def test_timeout_reports_partial_output():
    out = BashTool().run(command="echo early; sleep 5", timeout=1)
    assert "timed out" in out
    assert "early" in out


def test_no_output_success():
    assert BashTool().run(command="true") == "(no output)"


def test_timeout_is_clamped_to_max():
    out = BashTool().run(command="echo hi", timeout=99_999)
    assert out == "hi"


def test_bash_delegates_to_sandbox():
    from core.sandbox.base import CommandResult

    sandbox = RecordingSandbox(CommandResult(stdout="hi\n", stderr="", exit_code=0))
    out = BashTool(sandbox=sandbox).run(command="echo hi")
    assert out == "hi"
    assert sandbox.calls == [("echo hi", 120)]


def test_sandbox_error_renders_as_error_string_with_detail():
    from core.sandbox.base import SandboxError

    sandbox = RecordingSandbox(
        error=SandboxError(
            "command timed out after 1s", detail="\n--- partial stdout ---\nearly"
        )
    )
    out = BashTool(sandbox=sandbox).run(command="x", timeout=1)
    assert out == "Error: command timed out after 1s\n--- partial stdout ---\nearly"
