"""Built-in terminal tools: Read, Write, Edit, Glob, Grep, Bash."""
from typing import Optional

from core.tools.base import FileState, Tool, clip
from core.tools.registry import ToolRegistry


def register_builtins(registry: ToolRegistry, file_state: Optional[FileState] = None) -> None:
    """Register the six built-in terminal tools on a registry."""
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
    ):
        registry.register(tool)
