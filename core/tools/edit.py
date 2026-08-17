"""Edit tool: exact-match replacement with uniqueness enforcement."""
import difflib
from pathlib import Path

from core.tools.base import Tool


class EditTool(Tool):
    name = "Edit"
    description = (
        "Replace an exact string in a file. old_string must match the file "
        "content exactly and be unique unless replace_all is true. The file "
        "must have been Read earlier in this session."
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path of the file to edit",
            },
            "old_string": {
                "type": "string",
                "description": "Exact text to replace; must be unique unless replace_all",
            },
            "new_string": {"type": "string", "description": "Replacement text"},
            "replace_all": {
                "type": "boolean",
                "description": "Replace every occurrence instead of requiring uniqueness",
                "default": False,
            },
        },
        "required": ["file_path", "old_string", "new_string"],
    }
    requires_approval = True

    def run(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> str:
        if not old_string:
            return "Error: old_string must not be empty"
        path = Path(file_path)
        try:
            if not path.exists():
                return f"Error: file not found: {file_path}"
            if path.is_dir():
                return f"Error: {file_path} is a directory"
            if self.file_state is not None and not self.file_state.was_read(file_path):
                return (
                    f"Error: {file_path} has not been read this session; "
                    "use Read first"
                )
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            return f"Error: {e}"

        count = text.count(old_string)
        if count == 0:
            return f"Error: old_string not found in {file_path}"
        if count > 1 and not replace_all:
            return (
                f"Error: old_string matches {count} locations in {file_path}; "
                "provide more surrounding context or set replace_all"
            )

        new_text = text.replace(old_string, new_string) if replace_all else text.replace(
            old_string, new_string, 1
        )
        try:
            path.write_text(new_text, encoding="utf-8")
        except OSError as e:
            return f"Error: {e}"
        if self.file_state is not None:
            self.file_state.mark_read(file_path)

        diff = "\n".join(
            difflib.unified_diff(
                text.splitlines(),
                new_text.splitlines(),
                fromfile="before",
                tofile="after",
                lineterm="",
                n=1,
            )
        )
        replacements = count if replace_all else 1
        summary = f"Edited {file_path} ({replacements} replacement{'s' if replacements != 1 else ''})"
        return f"{summary}\n{diff}" if diff else summary
