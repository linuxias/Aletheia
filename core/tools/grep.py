"""Grep tool: regex search across files, stdlib re only."""
import fnmatch
import os
import re
from pathlib import Path
from typing import Iterator, Optional

from core.tools.base import Tool, clip
from core.tools.glob import SKIP_DIRS

MAX_MATCHES = 300
_SNIFF_BYTES = 1024
_MAX_FILE_BYTES = 10_000_000
_MODES = ("content", "files_with_matches", "count")


def _read_text(path: Path) -> Optional[str]:
    """File text, or None for binary/unreadable/oversized files."""
    try:
        with open(path, "rb") as f:
            head = f.read(_SNIFF_BYTES)
            if b"\x00" in head:
                return None
            rest = f.read()
    except OSError:
        return None
    if len(head) + len(rest) > _MAX_FILE_BYTES:
        return None
    return (head + rest).decode("utf-8", errors="replace")


class GrepTool(Tool):
    name = "Grep"
    description = (
        "Search file contents with a Python regular expression, recursively. "
        "Modes: content (path:lineno:line), files_with_matches (paths), "
        "count (path:N). Use include to filter file names, e.g. '*.py'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Python regular expression to search for",
            },
            "path": {
                "type": "string",
                "description": "File or directory to search in",
                "default": ".",
            },
            "mode": {
                "type": "string",
                "enum": list(_MODES),
                "description": "Output mode",
                "default": "content",
            },
            "include": {
                "type": "string",
                "description": "Glob filter for file names, e.g. '*.py'",
            },
        },
        "required": ["pattern"],
    }

    def run(
        self,
        pattern: str,
        path: str = ".",
        mode: str = "content",
        include: Optional[str] = None,
    ) -> str:
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"Error: invalid regex: {e}"
        if mode not in _MODES:
            return f"Error: invalid mode {mode!r} (expected one of: {', '.join(_MODES)})"

        base = Path(path)
        if base.is_file():
            candidates: Iterator[Path] = iter([base])
        elif base.is_dir():
            candidates = self._walk(base, include)
        else:
            return f"Error: path not found: {path}"

        results = []
        for fpath in candidates:
            text = _read_text(fpath)
            if text is None:
                continue
            count = 0
            for lineno, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    count += 1
                    if mode == "content":
                        results.append(f"{fpath}:{lineno}:{line.rstrip()}")
            if count:
                if mode == "files_with_matches":
                    results.append(str(fpath))
                elif mode == "count":
                    results.append(f"{fpath}:{count}")
            if len(results) >= MAX_MATCHES:
                break

        if not results:
            return "No matches found"
        out = "\n".join(results)
        if len(results) == MAX_MATCHES:
            out += f"\n(result list capped at {MAX_MATCHES} matches)"
        return clip(out)

    @staticmethod
    def _walk(base: Path, include: Optional[str]) -> Iterator[Path]:
        for root, dirs, files in os.walk(base):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for fname in sorted(files):
                if include and not fnmatch.fnmatch(fname, include):
                    continue
                yield Path(root) / fname
