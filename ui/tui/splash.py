"""Splash screen: ANSI Shadow wordmark plus real session facts."""
import os
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Optional, Tuple

from textual.app import ComposeResult
from textual.containers import Container
from textual.events import Resize
from textual.widgets import Static

WORDMARK: Tuple[str, ...] = (
    " █████╗ ██╗     ███████╗████████╗██╗  ██╗███████╗██╗ █████╗ ",
    "██╔══██╗██║     ██╔════╝╚══██╔══╝██║  ██║██╔════╝██║██╔══██╗",
    "███████║██║     █████╗     ██║   ███████║█████╗  ██║███████║",
    "██╔══██║██║     ██╔══╝     ██║   ██╔══██║██╔══╝  ██║██╔══██║",
    "██║  ██║███████╗███████╗   ██║   ██║  ██║███████╗██║██║  ██║",
    "╚═╝  ╚═╝╚══════╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝╚═╝  ╚═╝",
)

_TAGLINE = "truth as un-concealment"
_SUMMARY = "No tools, skills, or MCP servers configured yet — conversation only."

# Below this box width the 60-column wordmark + a 30-column info panel no
# longer fit beside each other (60 + 2 gap + 30 content + 4 chrome), so
# SplashView stacks the info panel under the wordmark (see styles.tcss).
_SIDE_BY_SIDE_MIN_WIDTH = 96

# The wordmark is a fixed 60 columns; below this box width it can only be
# rendered clipped mid-glyph, which looks like corruption rather than a logo.
_WORDMARK_MIN_WIDTH = 64


def git_branch() -> str:
    """Current branch name by reading .git/HEAD directly (follows the gitdir
    pointer in worktrees); walks cwd upwards; returns "" when not a repo. No subprocess."""
    directory = Path.cwd()
    while True:
        git = directory / ".git"
        head: Optional[Path] = None
        if git.is_dir():
            head = git / "HEAD"
        elif git.is_file():
            # Worktree: ".git" is a "gitdir: <path>" pointer file.
            pointer = git.read_text(encoding="utf-8").strip()
            gitdir_prefix = "gitdir: "
            if not pointer.startswith(gitdir_prefix):
                return ""
            head = Path(pointer[len(gitdir_prefix):]) / "HEAD"
        if head is not None and head.is_file():
            ref = head.read_text(encoding="utf-8").strip()
            ref_prefix = "ref: refs/heads/"
            if ref.startswith(ref_prefix):
                return ref[len(ref_prefix):]
            return ""  # detached HEAD
        if directory == directory.parent:
            return ""
        directory = directory.parent


def short_cwd() -> str:
    """Path.cwd() with the home directory replaced by '~'."""
    cwd = str(Path.cwd())
    home = str(Path.home())
    if cwd == home or cwd.startswith(home + os.sep):
        return "~" + cwd[len(home):]
    return cwd


def app_version() -> str:
    """Installed aletheia version ('0.0.0' when running from an unpacked tree)."""
    try:
        return version("aletheia")
    except PackageNotFoundError:
        return "0.0.0"


class SplashView(Container):
    """Rounded-border startup box: wordmark left, session info panel right.

    The panel deliberately shows only what the persistent chrome cannot: model
    lives in the composer's border subtitle and cwd/branch in the status bar,
    so repeating them here would just be dead weight in a box that scrolls
    away — and the rows they cost are what the hint bar needs at 80x24.
    """

    def __init__(self, *, protocol: str, session_id: str) -> None:
        super().__init__()
        self._protocol = protocol
        self._session_id = session_id

    @property
    def session_id(self) -> str:
        return self._session_id

    def compose(self) -> ComposeResult:
        from ui.tui.commands import COMMANDS  # deferred: keeps import order simple

        width = max(len(command.name) for command in COMMANDS) + 2
        info = "\n".join(
            [f"[$text-disabled]{label:<9}[/]{value}" for label, value in self._info_rows()]
            + [""]
            + [
                f"[$text-disabled]{command.name:<{width}}[/]{command.description}"
                for command in COMMANDS
            ]
        )
        with Container(id="splash-row"):
            yield Static("\n".join(WORDMARK), id="wordmark")
            yield Static(info, id="info")
        yield Static(_SUMMARY, id="summary")

    def on_resize(self, event: Resize) -> None:
        """Stack the info panel below the wordmark when side by side cannot fit,
        and drop the wordmark entirely once it could only be shown clipped."""
        self.set_class(event.size.width < _SIDE_BY_SIDE_MIN_WIDTH, "narrow")
        self.set_class(event.size.width < _WORDMARK_MIN_WIDTH, "tiny")

    def _info_rows(self) -> Tuple[Tuple[str, str], ...]:
        return (
            ("version", app_version()),
            ("tagline", _TAGLINE),
            ("protocol", self._protocol),
            ("session", self._session_id),
        )
