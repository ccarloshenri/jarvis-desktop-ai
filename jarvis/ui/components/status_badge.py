"""Small pill-shaped status chip. One font, one padding, colour per
semantic state.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from jarvis.ui import design


_STATE_STYLES = {
    # tuples of (background rgba alpha, border rgba alpha, text color).
    "active": (design.ACCENT_OK, 0.18, 0.55),
    "ready": (design.ACCENT_PRIMARY, 0.16, 0.45),
    "coming_soon": (design.ACCENT_WARM, 0.14, 0.45),
    "offline": (design.TEXT_MUTED, 0.12, 0.35),
    "error": (design.ACCENT_WARM, 0.18, 0.5),
    "neutral": (design.TEXT_SECONDARY, 0.10, 0.35),
}


class StatusBadge(QLabel):
    """Display a one-word status with palette coloured to match the
    semantic state. Use `set_state(state, text)` to flip both colour
    and label in sync."""

    def __init__(self, state: str = "neutral", text: str = "READY") -> None:
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(22)
        self.setContentsMargins(0, 0, 0, 0)
        self._state = state
        self.set_state(state, text)

    def set_state(self, state: str, text: str | None = None) -> None:
        accent, bg_alpha, border_alpha = _STATE_STYLES.get(
            state, _STATE_STYLES["neutral"]
        )
        if text is not None:
            self.setText(text.upper())
        self._state = state
        # Keep the stylesheet inline here — the state is dynamic and
        # needs to update without triggering a QSS reparse on the
        # parent tree. cheap and self-contained.
        self.setStyleSheet(
            f"""
            QLabel {{
                background-color: {accent.rgba_css(bg_alpha)};
                border: 1px solid {accent.rgba_css(border_alpha)};
                border-radius: 11px;
                color: {accent.hex};
                font-family: {design.FONT_UI};
                font-size: {design.FONT_SIZE_MICRO}px;
                font-weight: 700;
                letter-spacing: 3px;
                padding: 2px 10px;
            }}
            """
        )
