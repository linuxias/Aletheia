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
