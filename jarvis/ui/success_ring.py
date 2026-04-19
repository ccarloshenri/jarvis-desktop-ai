"""Circular donut chart — fills proportionally to the current success
ratio, with the percentage centred in Consolas. Fits the HUD aesthetic
better than a bar would, and reads at a glance across the room.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


class SuccessRing(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(140)
        self.setMinimumWidth(140)
        self._ratio = 1.0
        self._total = 0

    def set_success(self, successful: int, total: int) -> None:
        if total <= 0:
            ratio = 1.0
        else:
            ratio = max(0.0, min(1.0, successful / total))
        if ratio == self._ratio and total == self._total:
            return
        self._ratio = ratio
        self._total = total
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        size = min(self.width(), self.height()) - 12
        thickness = 12
        rect = QRectF(
            (self.width() - size) / 2,
            (self.height() - size) / 2,
            size,
            size,
        )

        # Background track: thin cyan ring so the "full" sweep is
        # always visible, even at 0% success.
        pen_bg = QPen(QColor(0, 255, 255, 40), thickness, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_bg)
        painter.drawArc(rect.adjusted(thickness / 2, thickness / 2, -thickness / 2, -thickness / 2), 0, 360 * 16)

        # Foreground arc — starts at 12 o'clock (90°), sweeps clockwise
        # by ratio. Cap round so the end of the arc looks intentional
        # rather than chopped off at a hard edge.
        span = int(-self._ratio * 360 * 16)
        color = _ratio_color(self._ratio)
        pen_fg = QPen(color, thickness, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_fg)
        painter.drawArc(
            rect.adjusted(thickness / 2, thickness / 2, -thickness / 2, -thickness / 2),
            90 * 16,
            span,
        )

        # Centre: big percentage + small label underneath. Two-pass
        # rendering keeps font size/colour independent.
        pct = int(round(self._ratio * 100))
        font = QFont("Consolas", 28)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(234, 252, 255))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{pct}%")

        painter.setFont(QFont("Bahnschrift", 9))
        painter.setPen(QColor(180, 220, 230, 180))
        label_rect = rect.adjusted(0, rect.height() / 2 + 14, 0, 0)
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, "SUCCESS")

        painter.end()


def _ratio_color(ratio: float) -> QColor:
    # Teal for healthy, amber for mixed, deep amber when most failed
    # — same palette as the rest of the HUD, no magenta.
    if ratio >= 0.85:
        return QColor(61, 245, 194, 240)
    if ratio >= 0.55:
        return QColor(255, 213, 107, 230)
    return QColor(255, 150, 60, 235)
