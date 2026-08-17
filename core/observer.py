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
