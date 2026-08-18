"""Scrolling conversation area."""
from rich.markup import escape

from textual.containers import ScrollableContainer
from textual.widgets import Markdown, Static

from ui.tui.splash import SplashView


class TranscriptView(ScrollableContainer):
    """Scrolling conversation area. The splash is its first child, so it scrolls
    away like normal history as the conversation grows."""

    def mount_splash(self, splash: SplashView) -> None:
        self.mount(splash)

    def _pinned(self) -> bool:
        """Whether the view sits within 2 lines of the bottom (the follow threshold)."""
        return self.scroll_y >= self.max_scroll_y - 2

    def append_user(self, text: str) -> None:
        """Static showing '❯ <text>' with the ❯ in cyan."""
        self.mount(Static(f"[cyan]❯[/cyan] {escape(text)}"))
        self.anchor(True)  # a user turn always brings the bottom into view

    def begin_assistant(self) -> Markdown:
        """Mount an empty Markdown widget for the incoming stream and return it."""
        markdown = Markdown("")
        self.mount(markdown)
        return markdown

    def append_note(self, text: str, *, error: bool = False) -> None:
        """Dim one-line note; error=True renders bold red."""
        # escape() so note text (user text, exception messages, bracket
        # literals like "[interrupted]") is never parsed as markup.
        if error:
            self.mount(Static(f"[bold red]{escape(text)}[/bold red]"))
        else:
            self.mount(Static(f"[dim]{escape(text)}[/dim]"))
        self.anchor(True)  # notes always bring the bottom into view

    def clear_conversation(self, splash: SplashView) -> None:
        """Remove every child and re-mount a fresh splash (used by /clear)."""
        self.remove_children()
        self.mount(splash)
        self.anchor(True)

    def autoscroll(self) -> None:
        """Follow the stream only if the view was pinned to the bottom.

        anchor() lets the framework re-scroll on every layout pass, so
        following survives late markdown re-pagination (a single
        scroll_end lands on a stale max_scroll_y); any user scroll
        releases the anchor, and scrolling back to the bottom re-engages it.
        """
        if self._pinned():
            self.anchor(True)
