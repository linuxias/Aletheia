from core.tools.bash import BashTool
from core.tools.registry import ToolRegistry


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
