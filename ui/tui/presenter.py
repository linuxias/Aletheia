"""Core↔UI bridge: runs Agent turns on worker threads, renders on the UI thread."""
import threading
import time
from functools import partial
from typing import TYPE_CHECKING, List, Optional

from textual.widgets import Input, Markdown

from core.agent import Agent, _arg_summary
from core.tools.base import Tool

from ui.tui.approval import ToolApprovalScreen
from ui.tui.status import HintBar, StatusBar
from ui.tui.transcript import TranscriptView

if TYPE_CHECKING:
    from ui.tui.app import AletheiaApp


# Tool output shown in the transcript is trimmed independently of the
# context-level clipping the tools apply themselves.
_DISPLAY_CHARS = 2000
_DISPLAY_LINES = 10


def _shorten(text: str, max_chars: int = _DISPLAY_CHARS, max_lines: int = _DISPLAY_LINES) -> str:
    if len(text) > max_chars:
        half = max_chars // 2
        text = (
            text[:half]
            + f"\n[... {len(text) - max_chars} characters truncated ...]\n"
            + text[-half:]
        )
    lines = text.splitlines()
    if len(lines) > max_lines:
        keep = max_lines // 2
        omitted = len(lines) - 2 * keep
        text = (
            "\n".join(lines[:keep])
            + f"\n[... {omitted} lines truncated ...]\n"
            + "\n".join(lines[-keep:])
        )
    return text


# A pending approval waits at most this long before denying; a worker must
# never block forever on a user who walked away.
_APPROVAL_TIMEOUT_S = 300.0


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
        self._hints = app.query_one(HintBar)
        self._input = app.query_one(Input)
        self._markdown: Optional[Markdown] = None
        self._buffer: List[str] = []  # throttled markdown buffer
        self._busy = False  # a turn is in flight
        self._turn_started = 0.0
        self._last_flush = 0.0
        self._approval_lock = threading.RLock()  # one approval modal at a time
        agent.ui = self
        agent.approver = self.confirm_tool
        self._cancel_requested = False  # set by request_cancel; unblocks a pending approval

    @property
    def busy(self) -> bool:
        return self._busy

    def submit(self, text: str) -> None:
        """Echo the user turn and run the turn; the assistant Markdown mounts lazily."""
        self._buffer = []
        self._last_flush = 0.0
        self._cancel_requested = False
        self._markdown = None
        self._busy = True
        self._turn_started = time.monotonic()
        self._transcript.append_user(text)
        self._status.set_state("thinking", turn_started=self._turn_started)
        self._hints.set_mode("busy")
        self._input.disabled = True
        self._app.run_worker(partial(self._run_turn, text), thread=True, exclusive=True)

    def request_cancel(self) -> None:
        """agent.request_cancel() — safe to call from the UI thread while the worker blocks.

        Also denies a pending approval ask and dismisses its modal: a
        cancelled turn must never still run a dangerous tool.
        """
        self._cancel_requested = True
        self._agent.request_cancel()
        screen = self._app.screen
        if isinstance(screen, ToolApprovalScreen):
            screen.dismiss(False)

    def confirm_tool(self, tool: Tool, args: dict) -> bool:
        """Approval gate for flagged tools, called on the worker thread.

        Blocks the worker until the user answers the modal. Cancel, app
        shutdown, and timeout all deny: running an unapproved dangerous
        tool must never be the fallback. Parallel subagents can ask at the
        same time; the lock serialises them into one modal at a time (the
        askers queue on it), so stacked modals never compete.
        """
        with self._approval_lock:
            if self._cancel_requested:
                return False  # a cancelled turn must not surface new modals
            return self._ask_approval(tool, args)

    def _ask_approval(self, tool: Tool, args: dict) -> bool:
        answered = threading.Event()
        answer: dict = {}

        def ask() -> None:
            def on_answer(allowed: bool | None) -> None:
                answer["allowed"] = bool(allowed)
                answered.set()

            self._app.push_screen(ToolApprovalScreen(tool.name, _arg_summary(args)), on_answer)

        try:
            self._app.call_from_thread(ask)
        except Exception:
            return False  # the app is shutting down; never run an unapproved tool
        deadline = time.monotonic() + _APPROVAL_TIMEOUT_S
        while not answered.wait(0.1):
            if self._cancel_requested or time.monotonic() > deadline:
                return False
        return answer.get("allowed", False)

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

    def tool_call(self, label: str, name: str, summary: str) -> None:
        self._app.call_from_thread(self._on_tool_call, label, name, summary)

    def tool_result(self, label: str, name: str, output: str, is_error: bool) -> None:
        self._app.call_from_thread(self._on_tool_result, label, name, output, is_error)

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
        text = "".join(self._buffer)
        if not text:
            self._transcript.append_note("(empty response)")
        else:
            self._transcript.append_note(self._stats(text))
        self._finish("ready")

    def _stats(self, text: str) -> str:
        """Per-turn footer: elapsed time and response size.

        Characters, not tokens: LLMClient.stream() yields text deltas only, so
        no usage figure reaches the Agent. Reporting a made-up token count
        would be worse than reporting an honest one we do have.
        """
        elapsed = time.monotonic() - self._turn_started
        return f"⏱ {elapsed:.1f}s · {len(text):,} chars"

    def _on_interrupted(self) -> None:
        self._flush(force=True)
        self._transcript.append_note("[interrupted]")
        self._finish("interrupted")

    def _on_tool_call(self, label: str, name: str, summary: str) -> None:
        self._flush(force=True)
        line = f"{self._agent_prefix(label)}{name} {summary}".rstrip()
        self._transcript.append_note(f"tool {line}")

    def _on_tool_result(self, label: str, name: str, output: str, is_error: bool) -> None:
        self._flush(force=True)
        body = output.strip() or "(no output)"
        prefix = "[tool error] " if is_error else ""
        who = self._agent_prefix(label)
        self._transcript.append_note(f"{prefix}{who}{name}: {_shorten(body)}", error=is_error)

    def _agent_prefix(self, label: str) -> str:
        """Subagent activity is tagged with its label; the main agent is not."""
        return f"[{label}] " if label != self._agent.label else ""

    def _on_error(self, error: Exception) -> None:
        self._flush(force=True)
        self._transcript.append_note(f"[error] {type(error).__name__}: {error}", error=True)
        self._finish(f"error: {type(error).__name__}")

    def _finish(self, state: str) -> None:
        self._busy = False
        self._status.set_state(state)
        self._hints.set_mode("interrupted" if state == "interrupted" else "idle")
        self._input.disabled = False
        self._input.focus()
