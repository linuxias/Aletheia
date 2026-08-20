"""Slash-command palette shown above the composer.

Ghost-text completion only finishes a command you already half-know; the
palette is what makes the surface browsable — press "/" and see everything,
with descriptions. It is also the extension point for the /model, /skills and
/mcp commands the roadmap implies.

Deliberately in normal flow rather than on a CSS layer: Textual 8 arranges each
layer group independently, so putting this on its own layer teleports the
composer to the top of the screen. In flow it steals rows from the transcript
(which is 1fr) and leaves the composer, status, and hint rows exactly where
they were — which is the property that matters.
"""
from typing import List, Sequence

from textual.widgets import OptionList
from textual.widgets.option_list import Option

from ui.tui.commands import Command, COMMANDS, lookup

# Taller than this and the palette starts eating the conversation; the list is
# scrollable, so a longer registry still works.
_MAX_ROWS = 6


class CommandPalette(OptionList):
    """Filtered command list. Never takes focus — see `AletheiaApp` for why."""

    def __init__(self) -> None:
        super().__init__(id="palette")
        self.can_focus = False  # focus stays in the Input; see show()
        self.display = False

    @staticmethod
    def matches(value: str) -> List[Command]:
        """Commands whose name or alias starts with the typed text.

        Only for input that starts with "/": prose must never pop a palette.
        """
        if not value.startswith("/"):
            return []
        typed, separator, _ = value.partition(" ")
        typed = typed.lower()
        if separator and lookup(typed) is not None:
            # The command is settled and the user has moved on to arguments;
            # a palette still hovering there would have nothing left to offer
            # (and would reopen itself the instant tab completed a name).
            return []
        return [
            command
            for command in COMMANDS
            if any(
                name.startswith(typed) for name in (command.name, *command.aliases)
            )
        ]

    def show(self, commands: Sequence[Command]) -> None:
        """Render `commands`, or hide entirely when there is nothing to offer."""
        if not commands:
            self.hide()
            return
        width = max(len(command.name) for command in commands) + 2
        self.clear_options()
        self.add_options(
            [
                Option(
                    f"{command.name:<{width}}[$text-disabled]{command.description}[/]",
                    id=command.name,
                )
                for command in commands
            ]
        )
        self.styles.height = min(len(commands), _MAX_ROWS)
        self.display = True
        self.highlighted = 0

    def hide(self) -> None:
        self.display = False
        self.highlighted = None

    @property
    def visible_now(self) -> bool:
        """Whether the palette is currently offering anything.

        Not named `visible`: Widget.visible is Textual's own CSS-visibility
        property and shadowing it breaks rendering.
        """
        return self.display and self.option_count > 0

    def move(self, delta: int) -> None:
        if not self.visible_now:
            return
        current = self.highlighted or 0
        self.highlighted = max(0, min(self.option_count - 1, current + delta))

    def chosen(self) -> str:
        """Name of the highlighted command ('' when nothing is highlighted)."""
        if not self.visible_now or self.highlighted is None:
            return ""
        return self.get_option_at_index(self.highlighted).id or ""
