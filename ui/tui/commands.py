"""Slash-command registry: the single source of dispatch, help text, and completion.

Names, aliases, and descriptions used to be split between a display-only tuple
and an if/elif ladder in app.py, so `/quit` was dispatchable but undocumented.
Everything that needs to know about a command reads this module, including the
splash panel — which is why the registry lives here and not in app.py, whose
import of SplashView would otherwise make the dependency circular.
"""
from typing import TYPE_CHECKING, Callable, Dict, NamedTuple, Optional, Tuple

if TYPE_CHECKING:
    from ui.tui.app import AletheiaApp


class Command(NamedTuple):
    name: str
    aliases: Tuple[str, ...]
    description: str
    handler: Callable[["AletheiaApp"], None]


COMMANDS: Tuple[Command, ...] = (
    Command("/help", (), "show this help", lambda app: app.cmd_help()),
    Command("/clear", (), "clear conversation history", lambda app: app.cmd_clear()),
    Command("/exit", ("/quit",), "quit the session", lambda app: app.exit()),
)

_BY_NAME: Dict[str, Command] = {
    name: command for command in COMMANDS for name in (command.name, *command.aliases)
}

def lookup(name: str) -> Optional[Command]:
    return _BY_NAME.get(name)
