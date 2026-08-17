"""Built-in terminal tools (Read, Glob, Grep; Write/Edit/Bash follow)."""
from typing import Optional

from core.tools.base import FileState, Tool, clip
from core.tools.registry import ToolRegistry


def register_builtins(registry: ToolRegistry, file_state: Optional[FileState] = None) -> None:
    """Register the built-in terminal tools on a registry."""
    from core.tools.glob import GlobTool
    from core.tools.grep import GrepTool
    from core.tools.read import ReadTool

    for tool in (
        ReadTool(file_state),
        GlobTool(),
        GrepTool(),
    ):
        registry.register(tool)
