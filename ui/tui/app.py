"""Full-screen Textual app: transcript, status bar, composer, and hint row."""
import time
import uuid
from typing import List, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Input, Static

from config import Config
from core.agent import Agent

from ui.tui.commands import COMMANDS, lookup
from ui.tui.palette import CommandPalette
from ui.tui.presenter import AgentPresenter
from ui.tui.prompt import PromptInput
from ui.tui.splash import SplashView, git_branch, short_cwd
from ui.tui.status import HintBar, StatusBar
from ui.tui.theme import RAMP_DEFAULTS, apply_theme
from ui.tui.transcript import TranscriptView

# Longest model name the composer's border subtitle shows before it is
# clipped by the border itself.
_MAX_SUBTITLE = 24

# A second ctrl+c within this window quits. Long enough to be a deliberate
# double-tap, short enough that a stray ctrl+c minutes later is harmless.
_QUIT_CONFIRM_WINDOW = 2.0


class AletheiaApp(App):
    """Full-screen conversational interface over a pre-built Agent."""

    CSS_PATH = "styles.tcss"
    # ctrl+c/ctrl+d are priority so they fire while the Input has focus: Input
    # itself binds ctrl+c to copy and ctrl+d to delete-character. escape and
    # up/down need no priority — Input binds none of them.
    BINDINGS = [
        Binding("ctrl+c", "interrupt_or_quit", "interrupt / quit", priority=True, show=False),
        Binding("ctrl+d", "maybe_exit", "exit", priority=True, show=False),
        Binding("escape", "escape", "interrupt / clear input", show=False),
        Binding("up", "history_prev", "previous prompt", show=False),
        Binding("down", "history_next", "next prompt", show=False),
        # tab is priority because Screen binds it to focus_next, which would
        # otherwise win; action_complete falls back to that when idle.
        Binding("tab", "complete", "accept completion", priority=True, show=False),
    ]

    def __init__(self, agent: Agent) -> None:
        super().__init__()
        self._agent = agent
        self.presenter: Optional[AgentPresenter] = None
        # Session facts are computed once so they survive /clear re-mounting.
        self.session_id = uuid.uuid4().hex[:8]
        self._cwd = short_cwd()
        self._branch = git_branch()
        # Submitted prompts, oldest first. _history_index == len(_history)
        # means "editing a fresh line"; _draft holds that fresh line while the
        # user browses backwards, so recalling history never eats a draft.
        self._history: List[str] = []
        self._history_index = 0
        self._draft = ""
        self._last_ctrl_c = 0.0
        # Text this app wrote into the Input itself (history recall, tab
        # completion) rather than the user typing. See _recall().
        self._recalled: Optional[str] = None

    def compose(self) -> ComposeResult:
        yield TranscriptView(id="transcript")
        yield CommandPalette()
        yield StatusBar(cwd=self._cwd, branch=self._branch)
        # One bordered object, not a stray glyph beside a bordered field:
        # Textual 8 removed Input's `prompt` parameter, so the "❯" is a Static
        # inside the composer's border rather than outside it.
        with Horizontal(id="composer"):
            yield Static("❯", id="prompt")
            # No `suggester=`: inline ghost text always shows the *first*
            # match, which silently contradicts the palette once the user
            # arrows down to a different one. The palette is strictly more
            # informative, so it is the only completion surface.
            yield PromptInput(placeholder="Ask a question, or / for commands", id="input")
        yield HintBar()

    def get_theme_variable_defaults(self) -> dict:
        """styles.tcss is parsed before on_mount registers the theme, so the
        identity ramp needs defaults here or `$aletheia-green*` are unresolved."""
        return dict(RAMP_DEFAULTS)

    def on_mount(self) -> None:
        apply_theme(self, "aletheia")
        self.presenter = AgentPresenter(app=self, agent=self._agent)
        self.query_one("#composer").border_subtitle = Config.MODEL[:_MAX_SUBTITLE]
        self.query_one(TranscriptView).mount_splash(self._make_splash())
        self.query_one(Input).focus()

    def _make_splash(self) -> SplashView:
        return SplashView(
            protocol=Config.PROTOCOL,
            session_id=self.session_id,
        )

    # ---- slash commands ----

    def cmd_help(self) -> None:
        transcript = self.query_one(TranscriptView)
        width = max(len(command.name) for command in COMMANDS) + 2
        for command in COMMANDS:
            alias = f" ({', '.join(command.aliases)})" if command.aliases else ""
            transcript.append_note(f"{command.name:<{width}}{command.description}{alias}")
        transcript.follow_to_end()

    def cmd_clear(self) -> None:
        self._agent.clear()
        self.query_one(TranscriptView).clear_conversation(self._make_splash())
        self.query_one(StatusBar).set_state("ready")
        self.query_one(HintBar).set_mode("idle")

    # ---- command palette ----

    def on_input_changed(self, event: Input.Changed) -> None:
        palette = self.query_one(CommandPalette)
        # Compared by value rather than cleared by a one-shot flag: setting the
        # Input to what it already held fires no Changed event at all, and a
        # dangling flag would then swallow the user's next real keystroke.
        if self._recalled is not None and event.value == self._recalled:
            self._recalled = None
            palette.hide()
            return
        if self._busy():
            palette.hide()
            return
        palette.show(CommandPalette.matches(event.value))

    def action_complete(self) -> None:
        """tab: accept the highlighted command, else Textual's focus_next."""
        palette = self.query_one(CommandPalette)
        chosen = palette.chosen()
        if not chosen:
            self.screen.focus_next()
            return
        self._recall(chosen + " ")  # trailing space: ready for future arguments
        palette.hide()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.clear()
        palette = self.query_one(CommandPalette)
        chosen = palette.chosen()
        palette.hide()
        # A prefix like "/cl" runs what the palette is pointing at; a fully
        # typed command falls through so any arguments survive.
        if chosen and lookup(text.split()[0] if text else "") is None:
            text = chosen
        if not text:
            return
        self._remember(text)
        if text.startswith("/"):
            command = lookup(text.split()[0])
            if command is None:
                # Unknown commands used to be sent to the LLM as a prompt,
                # which burned a request on an obvious typo.
                transcript = self.query_one(TranscriptView)
                transcript.append_note(
                    f"unknown command {text.split()[0]} — try /help", error=True
                )
                transcript.follow_to_end()
                return
            command.handler(self)
            return
        self.presenter.submit(text)

    # ---- prompt history ----

    def _remember(self, text: str) -> None:
        """Record a submitted line and rewind the history cursor to the end."""
        if not self._history or self._history[-1] != text:
            self._history.append(text)
        self._history_index = len(self._history)
        self._draft = ""

    def _recall(self, text: str) -> None:
        """Write `text` into the Input without waking the command palette.

        The palette is a response to *typing*. Recalling a command from history
        would otherwise reopen it, and an open palette consumes up/down — so
        one "/help" in the history froze every further ↑ on that entry.
        """
        self._recalled = text
        field = self.query_one(Input)
        field.value = text
        field.cursor_position = len(text)

    def action_history_prev(self) -> None:
        """Walk backwards through submitted prompts, shell style.

        The line being edited is stashed first, so ↑ from a half-typed prompt
        is recoverable with ↓ rather than destructive.
        """
        if self._palette_move(-1) or self._busy() or self._history_index == 0:
            return
        if self._history_index == len(self._history):
            self._draft = self.query_one(Input).value
        self._history_index -= 1
        self._recall(self._history[self._history_index])

    def _palette_move(self, delta: int) -> bool:
        """Steer the palette if it is open; True when the key was consumed."""
        palette = self.query_one(CommandPalette)
        if not palette.visible_now:
            return False
        palette.move(delta)
        return True

    def action_history_next(self) -> None:
        if self._palette_move(1) or self._busy() or self._history_index >= len(self._history):
            return
        self._history_index += 1
        if self._history_index == len(self._history):
            self._recall(self._draft)  # back to the stashed fresh line
        else:
            self._recall(self._history[self._history_index])

    # ---- key actions ----

    def _busy(self) -> bool:
        return self.presenter is not None and self.presenter.busy

    def action_escape(self) -> None:
        """Interrupt a running turn, else clear the input line.

        escape is the non-destructive half of what ctrl+c used to do alone: it
        can never end the session, so it is safe to hit reflexively.
        """
        palette = self.query_one(CommandPalette)
        if palette.visible_now:
            palette.hide()  # dismiss the palette without discarding the line
            return
        if self._busy():
            self.presenter.request_cancel()
            return
        self._cancel_quit_confirmation()
        self.query_one(Input).clear()

    def action_interrupt_or_quit(self) -> None:
        """Interrupt while busy; otherwise quit only on a confirmed double-tap.

        A single ctrl+c used to mean "stop generating" or "destroy my session"
        depending on a race the user could not see — pressing it a beat after
        the last token landed silently discarded the whole conversation.
        """
        if self._busy():
            self.presenter.request_cancel()
            return
        now = time.monotonic()
        if now - self._last_ctrl_c < _QUIT_CONFIRM_WINDOW:
            self.exit()
            return
        self._last_ctrl_c = now
        self.query_one(HintBar).set_mode("confirm_quit")
        self.set_timer(_QUIT_CONFIRM_WINDOW, self._expire_quit_confirmation)

    def _expire_quit_confirmation(self) -> None:
        if time.monotonic() - self._last_ctrl_c >= _QUIT_CONFIRM_WINDOW:
            self._cancel_quit_confirmation()

    def _cancel_quit_confirmation(self) -> None:
        self._last_ctrl_c = 0.0
        hints = self.query_one(HintBar)
        if hints.mode == "confirm_quit":
            hints.set_mode("interrupted" if self._interrupted() else "idle")

    def _interrupted(self) -> bool:
        return self.query_one(StatusBar).state == "interrupted"

    def action_maybe_exit(self) -> None:
        # Exit only when the input line is empty; never corrupt editing. This
        # stays a single press: it is the one-key escape hatch for people who
        # do not want ctrl+c's confirmation step.
        if not self.query_one(Input).value:
            self.exit()
