"""Card container — rounded, subtle inner glow, hover lift.

The stock QFrame looks flat against the HUD background; GlowFrame adds
a drop-shadow glow so cards read as raised surfaces.  Paired with a
hover variant (brighter border) we get the "tappable" feeling without
needing per-card button logic.
"""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect

from jarvis.ui import design


class GlowFrame(QFrame):
    """Card with a cyan drop-shadow glow.  `variant` picks between
    the default "card" look and the "selected" look used to highlight
    an active option (brighter border + stronger glow)."""

    def __init__(self, variant: str = "card") -> None:
        super().__init__()
        self._variant = variant
        self.setObjectName("glowCard")
        self._apply_base_style()
        self._apply_shadow()

    def set_variant(self, variant: str) -> None:
        if variant == self._variant:
            return
        self._variant = variant
        self._apply_base_style()
        self._apply_shadow()

    def _apply_base_style(self) -> None:
        if self._variant == "selected":
            border = design.ACCENT_PRIMARY.rgba_css(0.7)
            bg = design.SURFACE_RAISED.rgba_css(0.9)
        elif self._variant == "disabled":
            border = design.BORDER_SUBTLE.rgba_css(0.5)
            bg = design.SURFACE_SUNKEN.rgba_css(0.7)
        else:
            border = design.BORDER_SUBTLE.hex
            bg = design.SURFACE_CARD.rgba_css(0.85)
        self.setStyleSheet(
            f"""
            QFrame#glowCard {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: {design.RADIUS_LG}px;
            }}
            """
        )

    def _apply_shadow(self) -> None:
        shadow = QGraphicsDropShadowEffect(self)
        if self._variant == "selected":
            shadow.setBlurRadius(36)
            shadow.setColor(QColor(0, 240, 255, 110))
        else:
            shadow.setBlurRadius(22)
            shadow.setColor(QColor(0, 240, 255, 40))
        shadow.setOffset(0, 0)
        self.setGraphicsEffect(shadow)
