"""Compact status card for the HUD header strip.

Shows a labelled block with an accent "dot" and a primary value —
used to surface which LLM / TTS / Music provider is currently active
at the top of the dashboard. Reads at a glance.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from jarvis.ui import design


class StatusCard(QFrame):
    def __init__(self, label: str, value: str = "—", accent: str | None = None) -> None:
        super().__init__()
        self.setObjectName("statusCard")
        self._accent_color = accent or design.ACCENT_PRIMARY.hex

        root = QHBoxLayout(self)
        root.setContentsMargins(
            design.SPACE_4, design.SPACE_3, design.SPACE_4, design.SPACE_3
        )
        root.setSpacing(design.SPACE_3)

        self._dot = QLabel()
        self._dot.setFixedSize(10, 10)
        self._apply_dot_style()
        root.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignVCenter)

        text = QVBoxLayout()
        text.setSpacing(0)
        self._label = QLabel(label.upper())
        self._label.setStyleSheet(
            f"""
            color: {design.TEXT_MUTED.hex};
            font-family: {design.FONT_UI};
            font-size: {design.FONT_SIZE_MICRO}px;
            letter-spacing: 3px;
            """
        )
        self._value = QLabel(value)
        self._value.setStyleSheet(
            f"""
            color: {design.TEXT_PRIMARY.hex};
            font-family: {design.FONT_MONO};
            font-size: {design.FONT_SIZE_BODY}px;
            """
        )
        text.addWidget(self._label)
        text.addWidget(self._value)
        root.addLayout(text)
        root.addStretch(1)

        self.setStyleSheet(
            f"""
            QFrame#statusCard {{
                background-color: {design.SURFACE_CARD.rgba_css(0.7)};
                border: 1px solid {design.BORDER_SUBTLE.hex};
                border-radius: {design.RADIUS_MD}px;
            }}
            """
        )

    def set_value(self, value: str) -> None:
        self._value.setText(value)

    def set_accent(self, color_hex: str) -> None:
        self._accent_color = color_hex
        self._apply_dot_style()

    def _apply_dot_style(self) -> None:
        self._dot.setStyleSheet(
            f"""
            background-color: {self._accent_color};
            border-radius: 5px;
            max-width: 10px; max-height: 10px;
            min-width: 10px; min-height: 10px;
            """
        )
