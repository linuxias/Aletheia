"""Write tool: create or overwrite files (after a prior Read)."""
from pathlib import Path

from core.tools.base import Tool


class WriteTool(Tool):
    name = "Write"
    description = (
        "Create a file, or overwrite one that was read earlier in this "
        "session. Parent directories are created as needed. Existing files "
        "must be Read first; new files are always allowed."
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path of the file to write",
            },
            "content": {
                "type": "string",
                "description": "Full file content to write",
            },
        },
        "required": ["file_path", "content"],
    }
    requires_approval = True

    def run(self, file_path: str, content: str) -> str:
        path = Path(file_path)
        if (
            self.file_state is not None
            and path.exists()
            and not self.file_state.was_read(file_path)
        ):
            return (
                f"Error: {file_path} exists but has not been read this session; "
                "use Read first"
            )
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except OSError as e:
            return f"Error: {e}"
        if self.file_state is not None:
            self.file_state.mark_read(file_path)
        lines = len(content.splitlines())
        return f"Wrote {lines} line{'s' if lines != 1 else ''} to {file_path}"
