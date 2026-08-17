"""Read tool: numbered, line-ranged file contents."""
from pathlib import Path

from core.tools.base import Tool, clip

DEFAULT_LIMIT = 2000


class ReadTool(Tool):
    name = "Read"
    description = (
        "Read a text file from the local filesystem and return numbered "
        "lines (cat -n style). Use offset/limit to page through large "
        "files; a notice is appended when output was clipped."
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the file (absolute or relative)",
            },
            "offset": {
                "type": "integer",
                "description": "1-based line number to start from",
                "default": 1,
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of lines to return",
                "default": 2000,
            },
        },
        "required": ["file_path"],
    }

    def run(self, file_path: str, offset: int = 1, limit: int = DEFAULT_LIMIT) -> str:
        path = Path(file_path)
        try:
            if not path.exists():
                return f"Error: file not found: {file_path}"
            if path.is_dir():
                return f"Error: {file_path} is a directory"
            raw = path.read_bytes()
        except OSError as e:
            return f"Error: {e}"
        if b"\x00" in raw:
            return f"Error: {file_path} appears to be a binary file"

        lines = raw.decode("utf-8", errors="replace").splitlines()
        if not lines:
            if self.file_state is not None:
                self.file_state.mark_read(file_path)
            return "(file is empty)"

        start = max(1, int(offset))
        selected = lines[start - 1 : start - 1 + max(0, int(limit))]
        if not selected:
            return f"Error: offset {start} is past the end of the file ({len(lines)} lines)"

        numbered = [f"{n:>6}\t{line}" for n, line in enumerate(selected, start)]
        trailer = f"(showing lines {start}-{start + len(selected) - 1} of {len(lines)})"
        if self.file_state is not None:
            self.file_state.mark_read(file_path)
        return clip("\n".join(numbered) + "\n" + trailer)
