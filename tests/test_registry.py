import pytest

from core.tools import register_builtins
from core.tools.base import Tool
from core.tools.registry import ToolRegistry


class _DummyTool(Tool):
    name = "dummy"
    description = "a test tool"
    parameters = {"type": "object", "properties": {"x": {"type": "integer"}}}

    def run(self, x: int) -> str:
        return str(x)


def test_definitions_shape():
    registry = ToolRegistry()
    registry.register(_DummyTool())
    assert registry.definitions() == [
        {
            "name": "dummy",
            "description": "a test tool",
            "parameters": {"type": "object", "properties": {"x": {"type": "integer"}}},
        }
    ]


def test_execute_success():
    registry = ToolRegistry()
    registry.register(_DummyTool())
    assert registry.execute("dummy", {"x": 1}) == ("1", False)


def test_execute_unknown_tool():
    registry = ToolRegistry()
    output, is_error = registry.execute("nope", {})
    assert is_error and output.startswith("Error: unknown tool")


def test_execute_invalid_arguments():
    registry = ToolRegistry()
    registry.register(_DummyTool())
    output, is_error = registry.execute("dummy", {"x": 1, "bogus": 2})
    assert is_error and output.startswith("Error: invalid arguments")


def test_duplicate_registration_raises():
    registry = ToolRegistry()
    registry.register(_DummyTool())
    with pytest.raises(KeyError):
        registry.register(_DummyTool())


def test_register_builtins():
    registry = ToolRegistry()
    register_builtins(registry)
    assert set(registry.names()) == {"Read", "Write", "Edit", "Glob", "Grep", "Bash"}
    approval_required = {
        name for name in registry.names()
        if registry.get(name).requires_approval
    }
    assert approval_required == {"Write", "Edit", "Bash"}
