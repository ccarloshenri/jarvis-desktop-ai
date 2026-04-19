"""Scrolling waveform display for the captured mic.

Keeps a rolling history of the last ~2 seconds of level samples (at
12Hz from the capture callback) and renders them as a reflected
waveform — mirror top/bottom lines filled with a cyan gradient.

More informative than the segmented VU bar: you can actually see the
shape of your speech (peaks and valleys), idle periods, and the tail
as you wrap up a command.
"""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget


_HISTORY = 90  # ~3 seconds at the capture rate, enough to read the last phrase
_REPAINT_MS = 33


class WaveformWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(90)
        self.setMinimumWidth(360)
        self._history: deque[float] = deque([0.0] * _HISTORY, maxlen=_HISTORY)
        self._target = 0.0
        self._display = 0.0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(_REPAINT_MS)

    def set_level(self, level: float) -> None:
        self._target = max(0.0, min(1.0, float(level)))

    def _tick(self) -> None:
        # Ease the display level toward the target so the trace reads
        # smoothly even when the capture callback fires in bursts.
        if self._target > self._display:
            self._display += (self._target - self._display) * 0.55
        else:
            self._display += (self._target - self._display) * 0.22
        self._history.append(self._display)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = self.rect().adjusted(6, 6, -6, -6)
        painter.setPen(QPen(QColor(0, 255, 255, 30), 0.6))
        painter.drawRoundedRect(QRectF(rect), 6, 6)

        # Mid-line: reference baseline so silence reads as a flat line
        # instead of a jitter around zero.
        painter.setPen(QPen(QColor(0, 255, 255, 40), 0.8, Qt.PenStyle.DashLine))
        mid_y = rect.center().y()
        painter.drawLine(int(rect.left()), int(mid_y), int(rect.right()), int(mid_y))

        if not self._history:
            painter.end()
            return

        count = len(self._history)
        step = rect.width() / max(1, count - 1)
        half_h = rect.height() / 2 - 4

        # Build a closed polygon — top curve left-to-right, bottom curve
        # right-to-left — so we can fill it with a gradient.
        polygon = QPolygonF()
        for i, level in enumerate(self._history):
            x = rect.left() + i * step
            y = mid_y - level * half_h
            polygon.append(QPointF(x, y))
        for i in range(count - 1, -1, -1):
            x = rect.left() + i * step
            y = mid_y + self._history[i] * half_h
            polygon.append(QPointF(x, y))

        gradient = QLinearGradient(0, rect.top(), 0, rect.bottom())
        gradient.setColorAt(0.0, QColor(0, 255, 255, 150))
        gradient.setColorAt(0.5, QColor(0, 255, 255, 30))
        gradient.setColorAt(1.0, QColor(0, 255, 255, 150))
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(QColor(0, 255, 255, 220), 1.2))
        painter.drawPolygon(polygon)
        painter.end()
