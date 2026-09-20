"""Observer contract between the core Agent and any frontend."""
from typing import Protocol


class AgentObserver(Protocol):
    """Callbacks the Agent invokes while generating a response.

    Implementations may be called from a non-main thread; they must marshal
    to their own UI thread (see ui.tui.presenter.AgentPresenter).
    """

    def start_turn(self, label: str) -> None: ...

    def text_delta(self, label: str, text: str) -> None: ...

    def end_turn(self, label: str) -> None: ...

    def interrupted(self, label: str) -> None: ...

    def tool_call(self, label: str, name: str, summary: str) -> None: ...

    def tool_result(self, label: str, name: str, output: str, is_error: bool) -> None: ...


class NullObserver:
    """No-op observer for programmatic use (tests, scripts)."""

    def start_turn(self, label: str) -> None:
        pass

    def text_delta(self, label: str, text: str) -> None:
        pass

    def end_turn(self, label: str) -> None:
        pass

    def interrupted(self, label: str) -> None:
        pass

    def tool_call(self, label: str, name: str, summary: str) -> None:
        pass

    def tool_result(self, label: str, name: str, output: str, is_error: bool) -> None:
        pass


class SubagentObserver:
    """Observer wrapper for a subagent running inside a parent turn.

    Tool activity is forwarded (with the subagent's label) so the frontend
    can show what delegated work is doing. Text and turn-lifecycle events
    are swallowed: they belong to the parent's presentation — a subagent
    streaming into the parent's response buffer would interleave text —
    and the final report reaches the parent as the Task tool result anyway.
    """

    def __init__(self, parent: AgentObserver) -> None:
        self._parent = parent

    def start_turn(self, label: str) -> None:
        pass

    def text_delta(self, label: str, text: str) -> None:
        pass

    def end_turn(self, label: str) -> None:
        pass

    def interrupted(self, label: str) -> None:
        pass

    def tool_call(self, label: str, name: str, summary: str) -> None:
        self._parent.tool_call(label, name, summary)

    def tool_result(self, label: str, name: str, output: str, is_error: bool) -> None:
        self._parent.tool_result(label, name, output, is_error)
