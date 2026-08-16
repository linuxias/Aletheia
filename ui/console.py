from rich.console import Console as RichConsole
from rich.panel import Panel

_MAIN_COLOR = "bright_green"

# Single source for the slash commands shown in the banner and /help.
_COMMANDS = (
    ("/help", "show this help"),
    ("/clear", "clear conversation history"),
    ("/exit", "quit (/quit and Ctrl+D also work)"),
)


class ConsoleUI:
    def __init__(self):
        self.console = RichConsole()

    # ---------- start screen ----------
    def banner(self, model: str):
        commands = "  ".join(name for name, _ in _COMMANDS)
        self.console.print(
            Panel.fit(
                f"[bold]Model[/bold]: {model}\n"
                f"[dim]Commands: {commands}[/dim]",
                title="Aletheia",
                border_style=_MAIN_COLOR,
            )
        )

    def help(self):
        self.console.print(
            "\n".join(f"[bold]{name:<7}[/bold]{desc}" for name, desc in _COMMANDS)
        )

    def user_input(self) -> str:
        return self.console.input("[bold cyan]you>[/bold cyan] ")

    def start_turn(self, label: str):
        self.console.print(f"\n[bold {_MAIN_COLOR}]aletheia>[/bold {_MAIN_COLOR}] ", end="")

    def text_delta(self, label: str, text: str):
        self.console.print(text, end="", style=_MAIN_COLOR, highlight=False)

    def end_turn(self, label: str):
        self.console.print()

    def interrupted(self, label: str):
        self.console.print("\n[yellow][Interrupted by user][/yellow]")

    def info(self, message: str):
        self.console.print(f"[dim]{message}[/dim]")

    def error(self, message: str):
        self.console.print(f"[bold red]{message}[/bold red]")
