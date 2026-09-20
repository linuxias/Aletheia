"""Built-in tools: Read, Write, Edit, Glob, Grep, Bash, TodoWrite (+ Task wiring)."""
from typing import Optional

from core.tools.base import FileState, Tool, clip
from core.tools.registry import ToolRegistry
from core.tools.todo import TodoState, TodoWrite

__all__ = [
    "FileState",
    "Tool",
    "TodoState",
    "TodoWrite",
    "clip",
    "register_builtins",
]


def register_builtins(
    registry: ToolRegistry,
    file_state: Optional[FileState] = None,
    todo_state: Optional[TodoState] = None,
) -> None:
    """Register the session tools: the six terminal tools plus TodoWrite.

    Task is bound to a parent agent, so it is wired separately with
    core.tools.task.create_task_tool once the Agent exists.
    """
    from core.tools.bash import BashTool
    from core.tools.edit import EditTool
    from core.tools.glob import GlobTool
    from core.tools.grep import GrepTool
    from core.tools.read import ReadTool
    from core.tools.write import WriteTool

    for tool in (
        ReadTool(file_state),
        WriteTool(file_state),
        EditTool(file_state),
        GlobTool(),
        GrepTool(),
        BashTool(),
        TodoWrite(todo_state),
    ):
        registry.register(tool)
