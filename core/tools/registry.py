"""Registry of available tools: schema export + dispatch."""
from typing import Dict, List, Optional, Tuple

from core.tools.base import Tool


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise KeyError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def without(self, *names: str) -> "ToolRegistry":
        """A new registry sharing this one's Tool instances, minus `names`.

        Used to hand subagents the parent's tools without the Task tool,
        keeping delegation one level deep. The tools themselves (and any
        state they hold, e.g. FileState) are shared, not copied.
        """
        clone = ToolRegistry()
        for name, tool in self._tools.items():
            if name not in names:
                clone.register(tool)
        return clone

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def names(self) -> List[str]:
        return list(self._tools)

    def definitions(self) -> List[dict]:
        """Neutral tool definitions handed to the LLM adapters."""
        return [
            {"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in self._tools.values()
        ]

    def execute(self, name: str, arguments: dict) -> Tuple[str, bool]:
        """Run a tool; returns (output, is_error).

        Unknown tools and invalid arguments come back as error strings
        instead of exceptions so the model can adjust and retry.
        """
        tool = self._tools.get(name)
        if tool is None:
            return f"Error: unknown tool {name!r}", True
        try:
            return tool.run(**arguments), False
        except TypeError as e:
            return f"Error: invalid arguments for {name}: {e}", True
