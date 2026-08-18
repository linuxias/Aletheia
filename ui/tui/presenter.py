"""Core↔UI bridge: runs Agent turns on worker threads, renders on the UI thread."""
import time
from functools import partial
from typing import TYPE_CHECKING, List, Optional

from textual.widgets import Input, Markdown

from core.agent import Agent

from ui.tui.status import StatusBar
from ui.tui.transcript import TranscriptView

if TYPE_CHECKING:
    from ui.tui.app import AletheiaApp


class AgentPresenter:
    """Runs Agent turns on worker threads and renders observer callbacks on the UI thread.

    The Agent calls the AgentObserver methods from the worker thread; every
    method here only marshals work with app.call_from_thread(...) and never
    touches widgets directly.
    """

    def __init__(self, app: "AletheiaApp", agent: Agent) -> None:
        self._app = app
        self._agent = agent
        self._transcript = app.query_one(TranscriptView)
        self._status = app.query_one(StatusBar)
        self._input = app.query_one(Input)
        self._markdown: Optional[Markdown] = None
        self._buffer: List[str] = []  # throttled markdown buffer
        self._busy = False  # a turn is in flight
        self._turn_started = 0.0
        self._last_flush = 0.0
        agent.ui = self

    @property
    def busy(self) -> bool:
        return self._busy

    def submit(self, text: str) -> None:
        """Echo the user turn and run the turn; the assistant Markdown mounts lazily."""
        self._buffer = []
        self._last_flush = 0.0
        self._markdown = None
        self._busy = True
        self._turn_started = time.monotonic()
        self._transcript.append_user(text)
        self._status.set_state("thinking", turn_started=self._turn_started)
        self._input.disabled = True
        self._app.run_worker(partial(self._run_turn, text), thread=True, exclusive=True)

    def request_cancel(self) -> None:
        """agent.request_cancel() — safe to call from the UI thread while the worker blocks."""
        self._agent.request_cancel()

    # ---- AgentObserver (worker thread) ----

    def start_turn(self, label: str) -> None:
        pass  # the thinking state was already set by submit() on the UI thread

    def text_delta(self, label: str, text: str) -> None:
        self._buffer.append(text)
        self._app.call_from_thread(self._flush)

    def end_turn(self, label: str) -> None:
        self._app.call_from_thread(self._on_end)

    def interrupted(self, label: str) -> None:
        self._app.call_from_thread(self._on_interrupted)

    # ---- worker body (worker thread) ----

    def _run_turn(self, text: str) -> None:
        try:
            self._agent.run(text)  # output was already streamed; return value unused
        except Exception as e:
            self._app.call_from_thread(self._on_error, e)

    # ---- internals (UI thread, via call_from_thread) ----

    def _flush(self, force: bool = False) -> None:
        """Markdown.update(''.join(buffer)) at most every 0.1 s; force=True on end/interrupt/error."""
        if not self._app.is_running:
            return  # app is shutting down; further Markdown updates only flood stderr
        # Lazy assistant slot: an empty Markdown("") renders ~4 rows tall, which
        # would inflate the submit jump and show a blank block before the first
        # token — so the widget only mounts once text actually arrives.
        if self._markdown is None and self._buffer:
            self._markdown = self._transcript.begin_assistant()
        now = time.monotonic()
        if not force and now - self._last_flush < 0.1:
            return
        self._last_flush = now
        if self._markdown is not None:
            self._markdown.update("".join(self._buffer))
        self._transcript.autoscroll()

    def _on_end(self) -> None:
        self._flush(force=True)
        if not "".join(self._buffer):
            self._transcript.append_note("(empty response)")
        self._finish("ready")

    def _on_interrupted(self) -> None:
        self._flush(force=True)
        self._transcript.append_note("[interrupted]")
        self._finish("interrupted")

    def _on_error(self, error: Exception) -> None:
        self._flush(force=True)
        self._transcript.append_note(f"[error] {type(error).__name__}: {error}", error=True)
        self._finish(f"error: {type(error).__name__}")

    def _finish(self, state: str) -> None:
        self._busy = False
        self._status.set_state(state)
        self._input.disabled = False
        self._input.focus()
