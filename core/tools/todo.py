"""TodoWrite tool: the session's live plan for multi-step work.

The model owns a checklist (an experiment campaign, a fix, a survey) and
keeps it current by replacing the whole list on every call — the semantics
Claude Code's TodoWrite established. The rendered checklist comes back as
the tool result, so the plan stays visible in the conversation history
without extra context-injection machinery.
"""
from typing import List, Optional

from core.tools.base import Tool

_STATUSES = ("pending", "in_progress", "completed")
_MARKS = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]"}


class TodoState:
    """Session-scoped todo list, shared between the tool and the frontend."""

    def __init__(self) -> None:
        self.todos: List[dict] = []

    def set_todos(self, todos: List[dict]) -> Optional[str]:
        """Validate and replace the whole list; returns an error message or None."""
        if not isinstance(todos, list):
            return "Error: todos must be an array"
        for i, item in enumerate(todos):
            if not isinstance(item, dict):
                return f"Error: todo #{i + 1} must be an object"
            subject = item.get("subject")
            if not isinstance(subject, str) or not subject.strip():
                return f"Error: todo #{i + 1} needs a non-empty 'subject'"
            if item.get("status") not in _STATUSES:
                expected = ", ".join(_STATUSES)
                return (
                    f"Error: todo #{i + 1} has invalid status {item.get('status')!r}; "
                    f"expected one of: {expected}"
                )
        self.todos = todos
        return None

    def render(self) -> str:
        if not self.todos:
            return "(no todos)"
        lines = []
        for item in self.todos:
            subject = item["subject"]
            if item["status"] == "in_progress" and item.get("activeForm"):
                subject = f"{item['activeForm']} ({subject})"
            line = f"{_MARKS[item['status']]} {subject}"
            if item.get("description"):
                line += f" — {item['description']}"
            lines.append(line)
        return "\n".join(lines)


class TodoWrite(Tool):
    name = "TodoWrite"
    description = (
        "Create or update the session todo list — the detailed plan for "
        "multi-step work such as an experiment campaign. Each call REPLACES "
        "the entire list: send every todo, not just the changed ones. Keep "
        "exactly one todo in_progress while working on it, mark todos "
        "completed the moment they finish (never in a batch at the end), and "
        "revise the plan when the work changes direction. The updated "
        "checklist is returned as the result."
    )
    parameters = {
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "description": "The full, updated todo list",
                "items": {
                    "type": "object",
                    "properties": {
                        "subject": {"type": "string", "description": "What needs to be done"},
                        "description": {
                            "type": "string",
                            "description": "Details: method, files, success criteria",
                        },
                        "status": {
                            "type": "string",
                            "enum": list(_STATUSES),
                        },
                        "activeForm": {
                            "type": "string",
                            "description": "Present-progress label shown while in_progress",
                        },
                    },
                    "required": ["subject", "status"],
                },
            },
        },
        "required": ["todos"],
    }

    def __init__(self, todo_state: Optional[TodoState] = None):
        super().__init__()
        self.todo_state = todo_state or TodoState()

    def run(self, todos: List[dict]) -> str:
        error = self.todo_state.set_todos(todos)
        if error is not None:
            return error
        return self.todo_state.render()
