"""Scrolling conversation area."""
import time

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

    def _follow_if_overflow(self) -> None:
        """Anchor to the bottom only when content overflows the viewport.

        Anchoring while everything still fits bottom-pins the content
        (negative scroll_y, blank rows ABOVE it) — the "screen slides down"
        bug. With room to spare the view stays top-aligned and does not move.
        """
        if self.max_scroll_y > 0:
            self.anchor(True)

    def append_user(self, text: str) -> None:
        """Static showing '❯ <text>' with the ❯ in cyan."""
        self.mount(Static(f"[cyan]❯[/cyan] {escape(text)}"))
        # Decide after layout so the just-mounted echo is accounted for:
        # follow when it overflows, otherwise the view does not move.
        self.call_after_refresh(self._follow_if_overflow)

    def begin_assistant(self) -> Markdown:
        """Mount an empty Markdown widget for the incoming stream and return it."""
        markdown = Markdown("")
        self.mount(markdown)
        return markdown

    def append_note(self, text: str, *, error: bool = False) -> None:
        """Dim one-line note; error=True renders bold red."""
        # escape() so note text (user text, exception messages, bracket
        # literals like "[interrupted]") is never parsed as markup.
        # No scroll: notes land at the end of a turn — visible when following,
        # and a user who scrolled up is never yanked.
        if error:
            self.mount(Static(f"[bold red]{escape(text)}[/bold red]"))
        else:
            self.mount(Static(f"[dim]{escape(text)}[/dim]"))

    def clear_conversation(self, splash: SplashView) -> None:
        """Remove every child and re-mount a fresh splash (used by /clear)."""
        self.remove_children()
        self.mount(splash)
        self.anchor(False)
        self.scroll_to(y=0, animate=False)  # fresh conversation is top-aligned

    def autoscroll(self) -> None:
        """Follow the stream only if the view was pinned, once content overflows.

        anchor() makes the compositor re-scroll on every layout pass, so
        following survives late markdown re-pagination; any user scroll releases
        the anchor, and scrolling back to the bottom re-engages it. The anchor
        must NOT be engaged while content still fits the viewport (the
        compositor would bottom-pin it: blank rows above, negative scroll).
        The overflow check runs after layout and retries against a wall-clock
        deadline: a Markdown update re-paginates asynchronously, and a fixed
        number of refresh retries exhausts under CPU load while a fast
        (sub-throttle) stream never flushes again.
        """
        was_pinned = self._pinned()

        def follow(deadline: float) -> None:
            if not was_pinned:
                return
            # The user scrolled since this follow was scheduled: honour the
            # gesture instead of yanking the view back to the bottom.
            if self._anchor_released:
                return
            if self.max_scroll_y > 0:
                self.anchor(True)
            elif time.monotonic() < deadline:
                self.call_after_refresh(follow, deadline)

        self.call_after_refresh(follow, time.monotonic() + 1.0)
