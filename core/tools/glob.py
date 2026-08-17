"""Glob tool: find files by pattern, newest first."""
from pathlib import Path

from core.tools.base import Tool

SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules"}
MAX_ENTRIES = 500


class GlobTool(Tool):
    name = "Glob"
    description = (
        "Find files matching a glob pattern (e.g. '**/*.py'), recursively, "
        "sorted by modification time (newest first)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern, e.g. '**/*.py'",
            },
            "path": {
                "type": "string",
                "description": "Directory to search in",
                "default": ".",
            },
        },
        "required": ["pattern"],
    }

    def run(self, pattern: str, path: str = ".") -> str:
        base = Path(path)
        try:
            if not base.is_dir():
                return f"Error: {path} is not a directory"
            matches = [p for p in base.glob(pattern) if p.is_file()]
        except (OSError, ValueError) as e:
            return f"Error: {e}"

        entries = []
        for p in matches:
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            entries.append((mtime, str(p)))
        entries.sort(key=lambda e: (-e[0], e[1]))

        if not entries:
            return "No files found"
        listed = [name for _, name in entries[:MAX_ENTRIES]]
        out = "\n".join(listed)
        if len(entries) > MAX_ENTRIES:
            out += f"\n(showing 1-{MAX_ENTRIES} of {len(entries)} files)"
        return out
