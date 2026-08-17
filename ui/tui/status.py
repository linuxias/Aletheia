"""One-line status bar shown under the transcript."""
import time
from typing import Optional

from textual.widgets import Static

_ACCENT = "#00ff00"  # same color as $accent in styles.tcss


class StatusBar(Static):
    """One-line state bar: '─ <state> │ <model> │ <uptime>s │ <cwd> (<branch>)'."""

    def __init__(self, model: str, cwd: str, branch: str) -> None:
        super().__init__(id="status")
        self._model = model
        self._cwd = cwd
        self._branch = branch
        self._started = time.monotonic()
        self._state = "ready"
        self._turn_started: Optional[float] = None
        self.update(self._line())

    @property
    def state(self) -> str:
        """Current state: 'ready' / 'thinking' / 'interrupted' / 'error: <Type>'."""
        return self._state

    def set_state(self, state: str, *, turn_started: Optional[float] = None) -> None:
        self._state = state
        self._turn_started = turn_started
        self.update(self._line())

    def tick(self) -> None:
        """Recompute the line (called by the App's 1 s interval)."""
        self.update(self._line())

    def _line(self) -> str:
        now = time.monotonic()
        if self._state == "thinking":
            state = f"thinking… {int(now - (self._turn_started or now))}s"
        else:
            state = self._state
        line = f"{self._model} │ {int(now - self._started)}s │ {self._cwd}"
        if self._branch:
            line += f" ({self._branch})"
        return f"─ [{_ACCENT}]{state}[/] │ {line}"
