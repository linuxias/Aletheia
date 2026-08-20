"""Status bar and keyboard-hint row shown under the transcript."""
import time
from typing import Optional

from rich.cells import cell_len

from textual.events import Resize
from textual.widgets import Static

# One frame per _TICK while a turn runs. A once-per-second integer is not a
# liveness signal — during a slow first token the UI looked frozen for a full
# second at a time.
_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_TICK = 0.1

# The verb rotates so a long turn reads as "time passing is expected" rather
# than "stuck". Aletheia's register: unconcealment, not "crunching".
_VERBS = ("Thinking", "Reasoning", "Considering", "Unconcealing", "Composing", "Weighing")
_VERB_PERIOD = 2.5

# Below this width the right-hand cwd/branch block is dropped rather than
# wrapped: a status bar that wraps to two rows would push the composer down,
# which is the class of layout jump commit d7a1f2f fixed.
_MIN_WIDTH_FOR_CONTEXT = 70

# The dot is the one element on this row that carries meaning, so it encodes the
# state: reporting a failed turn with the success colour is a semantic bug
# independent of any palette.
_STATE_COLOUR = {"interrupted": "$warning"}


def _dot_colour(state: str) -> str:
    if state.startswith("error"):
        return "$error"
    return _STATE_COLOUR.get(state, "$aletheia-green-soft")


class StatusBar(Static):
    """One-line state bar: '<spinner> <state>' left, '<cwd> (<branch>)' right.

    The model is deliberately absent — it lives in the composer's border
    subtitle, where it is equally always-visible but does not compete with the
    one thing on this row that actually changes.
    """

    def __init__(self, cwd: str, branch: str) -> None:
        super().__init__(id="status")
        self._cwd = cwd
        self._branch = branch
        self._state = "ready"
        self._turn_started: Optional[float] = None
        self._timer = None
        # Static needs a renderable before its first layout pass; self.size is
        # (0, 0) until mount, so this first line is the narrow (left-only) form.
        self._refresh_line()

    def on_mount(self) -> None:
        # Paused at construction: an always-running 10 Hz timer would spin the
        # CPU in headless tests and while the app sits idle.
        self._timer = self.set_interval(_TICK, self._refresh_line, pause=True)
        self._refresh_line()

    def on_resize(self, event: Resize) -> None:
        self._refresh_line()

    @property
    def state(self) -> str:
        """Current state: 'ready' / 'thinking' / 'interrupted' / 'error: <Type>'."""
        return self._state

    def set_state(self, state: str, *, turn_started: Optional[float] = None) -> None:
        self._state = state
        self._turn_started = turn_started
        if self._timer is not None:
            self._timer.resume() if state == "thinking" else self._timer.pause()
        self._refresh_line()

    # NB: not named _render — Widget._render() is Textual's own hook and
    # overriding it makes the widget render as None.
    def _refresh_line(self) -> None:
        # layout=False so a 10 Hz spinner repaint never triggers a layout pass:
        # reflowing the transcript ten times a second would race the anchor
        # logic in TranscriptView.autoscroll().
        self.update(self._line(), layout=False)

    def _left(self) -> str:
        if self._state == "thinking":
            elapsed = time.monotonic() - (self._turn_started or time.monotonic())
            frame = _FRAMES[int(time.monotonic() / _TICK) % len(_FRAMES)]
            verb = _VERBS[int(elapsed / _VERB_PERIOD) % len(_VERBS)]
            return (
                f"[$aletheia-green-soft]{frame}[/] {verb}… {int(elapsed)}s "
                f"[$text-disabled]· esc to interrupt[/]"
            )
        return f"[{_dot_colour(self._state)}]●[/] {self._state}"

    def _plain_left(self) -> str:
        """_left() without markup, for width arithmetic."""
        if self._state == "thinking":
            elapsed = time.monotonic() - (self._turn_started or time.monotonic())
            verb = _VERBS[int(elapsed / _VERB_PERIOD) % len(_VERBS)]
            return f"X {verb}… {int(elapsed)}s · esc to interrupt"
        return f"● {self._state}"

    def _line(self) -> str:
        left = self._left()
        width = self.size.width
        if width < _MIN_WIDTH_FOR_CONTEXT:
            return left
        right = self._cwd + (f" ({self._branch})" if self._branch else "")
        # cell_len, not len: a CJK path is twice as wide as its character count,
        # so len() overestimated the gap and pushed the whole right-hand block
        # off the end of the widget — a Korean cwd vanished entirely.
        gap = width - cell_len(self._plain_left()) - cell_len(right)
        if gap < 2:
            return left
        return f"{left}{' ' * gap}[$text-disabled]{right}[/]"


class HintBar(Static):
    """Contextual keyboard hints under the composer.

    Ctrl+C's two meanings (interrupt while busy, quit while idle) were
    previously documented only inside /help and the splash — and the splash
    scrolls away permanently. The interrupt affordance is what a user needs
    most mid-stream, so it is stated on the row where they are already looking.
    """

    #: Every string must stay under 70 columns: a wrapping hint bar would make
    #: the composer jump by a row.
    HINTS = {
        "idle": "enter send · ↑ history · / commands · ctrl+d quit",
        "busy": "streaming… · esc interrupt",
        # "↑ to recall", not "enter to resend": submit() clears the input, so a
        # bare enter has nothing to re-send — and a modal enter after an
        # interrupt would fire a request on a mistyped keystroke.
        "interrupted": "interrupted · ↑ to recall and edit · enter to send",
        "confirm_quit": "press ctrl+c again to quit · esc to stay",
    }

    def __init__(self) -> None:
        super().__init__(id="hints")
        self._mode = "idle"
        self.set_mode(self._mode)

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        self._mode = mode if mode in self.HINTS else "idle"
        self.update(self.HINTS[self._mode])
