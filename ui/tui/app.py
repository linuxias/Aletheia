"""Full-screen Textual app: transcript, status bar, and input line."""
import uuid
from typing import Optional, Tuple

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Input, Static

from config import Config
from core.agent import Agent

from ui.tui.presenter import AgentPresenter
from ui.tui.splash import SplashView, git_branch, short_cwd
from ui.tui.status import StatusBar
from ui.tui.transcript import TranscriptView

COMMANDS: Tuple[Tuple[str, str], ...] = (
    ("/help", "show this help"),
    ("/clear", "clear conversation history"),
    ("/exit", "quit (/quit, Ctrl+C, Ctrl+D also work)"),
)


class AletheiaApp(App):
    """Full-screen conversational interface over a pre-built Agent."""

    CSS_PATH = "styles.tcss"
    # Both bindings are priority so they fire while the Input has focus.
    BINDINGS = [
        Binding("ctrl+c", "interrupt", "interrupt / quit", priority=True, show=False),
        Binding("ctrl+d", "maybe_exit", "exit", priority=True, show=False),
    ]

    def __init__(self, agent: Agent) -> None:
        super().__init__()
        self._agent = agent
        self.presenter: Optional[AgentPresenter] = None
        # Session facts are computed once so they survive /clear re-mounting.
        self.session_id = uuid.uuid4().hex[:8]
        self._cwd = short_cwd()
        self._branch = git_branch()

    def compose(self) -> ComposeResult:
        yield TranscriptView(id="transcript")
        yield StatusBar(model=Config.MODEL, cwd=self._cwd, branch=self._branch)
        # Textual 8 removed Input's `prompt` parameter, so the "❯ " glyph
        # from the design is a Static beside the input.
        with Horizontal(id="input-row"):
            yield Static("❯", id="prompt")
            yield Input(placeholder="Ask me anything…", id="input")

    def on_mount(self) -> None:
        self.presenter = AgentPresenter(app=self, agent=self._agent)
        self.query_one(TranscriptView).mount_splash(self._make_splash())
        self.query_one(Input).focus()
        self.set_interval(1.0, self.query_one(StatusBar).tick)

    def _make_splash(self) -> SplashView:
        return SplashView(
            model=Config.MODEL,
            protocol=Config.PROTOCOL,
            session_id=self.session_id,
            cwd=self._cwd,
            branch=self._branch,
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.clear()
        if not text:
            return
        if text in ("/exit", "/quit"):
            self.exit()
        elif text == "/help":
            transcript = self.query_one(TranscriptView)
            for name, desc in COMMANDS:
                transcript.append_note(f"{name:<8}{desc}")
        elif text == "/clear":
            self._agent.clear()
            self.query_one(TranscriptView).clear_conversation(self._make_splash())
            self.query_one(StatusBar).set_state("ready")
        else:
            self.presenter.submit(text)

    def action_interrupt(self) -> None:
        if self.presenter is not None and self.presenter.busy:
            self.presenter.request_cancel()
        else:
            self.exit()

    def action_maybe_exit(self) -> None:
        # Exit only when the input line is empty; never corrupt editing.
        if not self.query_one(Input).value:
            self.exit()
