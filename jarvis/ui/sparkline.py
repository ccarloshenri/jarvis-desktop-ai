"""Mini bar chart for the HUD's latency history panel.

Draws N recent values as vertical bars spanning the widget height.
Values are auto-scaled to the max of the current window so a slow turn
stretches the bar all the way up relative to its peers — good at a
glance, no need to read axis labels.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class Sparkline(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(44)
        self.setMinimumWidth(220)
        self._values: tuple[int, ...] = ()

    def set_values(self, values: Sequence[int]) -> None:
        clean = tuple(max(0, int(v)) for v in values)
        if clean == self._values:
            return
        self._values = clean
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802  (Qt API name)
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = self.rect().adjusted(6, 4, -6, -4)
        painter.setPen(QPen(QColor(0, 255, 255, 40), 0.8))
        painter.drawRoundedRect(QRectF(rect), 4, 4)

        if not self._values:
            painter.setPen(QColor(200, 230, 240, 120))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "sem dados ainda")
            painter.end()
            return

        peak = max(self._values) or 1
        count = len(self._values)
        spacing = 2
        bar_w = max(2.0, (rect.width() - spacing * (count - 1)) / count)
        baseline = rect.bottom() - 2
        usable_h = rect.height() - 4

        for i, value in enumerate(self._values):
            ratio = value / peak
            h = max(2.0, ratio * usable_h)
            x = rect.left() + i * (bar_w + spacing)
            y = baseline - h
            bar_rect = QRectF(x, y, bar_w, h)
            # Colour hot bars amber so outliers jump out; normal bars
            # stay cyan. Amber keeps the whole HUD in the cyan/amber
            # family rather than breaking pattern with a pink accent.
            color = _bar_color(ratio)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(bar_rect, 1.5, 1.5)

        # Peak label top-right so the user can see the scale without a
        # full axis — cheaper to read than a grid.
        painter.setPen(QColor(200, 230, 240, 180))
        painter.drawText(
            rect.adjusted(0, 2, -4, 0),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
            f"{peak} ms",
        )
        painter.end()


def _bar_color(ratio: float) -> QColor:
    if ratio < 0.55:
        return QColor(0, 240, 255, 200)
    if ratio < 0.85:
        return QColor(110, 234, 255, 215)
    return QColor(255, 213, 107, 230)
