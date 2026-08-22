"""Yes/No modal shown before a dangerous tool (Write/Edit/Bash) is allowed to run."""
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ToolApprovalScreen(ModalScreen[bool]):
    """Ask whether one flagged tool may run; dismisses True (allow) or False (deny).

    Deny is the Enter default (AUTO_FOCUS): approving a dangerous tool must
    be a deliberate choice, never the fallback. ctrl+c is a priority app
    binding, so it goes to the app's interrupt path instead; the presenter
    dismisses this screen from there.
    """

    AUTO_FOCUS = "#deny"
    BINDINGS = [
        ("y", "allow", "Allow"),
        ("n", "deny", "Deny"),
        ("escape", "deny", "Deny"),
    ]

    def __init__(self, tool_name: str, summary: str) -> None:
        super().__init__()
        self._tool_name = tool_name
        self._summary = summary

    def compose(self) -> ComposeResult:
        with Vertical(id="approval-dialog"):
            yield Static(
                f"allow {self._tool_name} {self._summary}".rstrip(),
                id="approval-question",
            )
            with Horizontal(id="approval-buttons"):
                yield Button("Allow (y)", id="allow", variant="warning")
                yield Button("Deny (n)", id="deny", variant="error")

    def action_allow(self) -> None:
        self.dismiss(True)

    def action_deny(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "allow")
