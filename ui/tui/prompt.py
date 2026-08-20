"""The composer's text field — fixes CJK scroll and NFD input bugs."""
import unicodedata

from rich.cells import cell_len

from textual.widgets import Input

_TAB_WIDTH = 4


class PromptInput(Input):
    """Input with CJK-safe scroll snapping and NFC normalisation."""

    def validate_scroll_x(self, value: float) -> float:
        value = super().validate_scroll_x(value)
        if value <= 0:
            return value
        return float(self._char_boundary_at_or_after(value))

    def _char_boundary_at_or_after(self, cell: float) -> int:
        offset = 0
        for character in self.value:
            if offset >= cell:
                return offset
            if character == "\t":
                offset += _TAB_WIDTH - (offset % _TAB_WIDTH)
            else:
                offset += cell_len(character)
        return offset

    def insert_text_at_cursor(self, text: str) -> None:
        super().insert_text_at_cursor(unicodedata.normalize("NFC", text))

    def _on_paste(self, event) -> None:  # type: ignore[override]
        if event.text:
            event.text = unicodedata.normalize("NFC", event.text)
        super()._on_paste(event)
