"""Horizontal event ribbon — last N interaction outcomes plotted as
colour-coded dots. Gives a visual rhythm ("how often did I use
Jarvis lately, how many failed") without having to read a log.

Dot colours reuse the HUD palette:
    cyan   — completed turn
    amber  — unintelligible / error turn
    teal   — wake fire (listening started)

Newest event goes on the right, scrolling the older ones off the
left. No real time axis is drawn — the density itself is the
information.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from jarvis.ui import design


_CAPACITY = 40
_DOT_SIZE = 10
_DOT_SPACING = 4


@dataclass(frozen=True, slots=True)
class Event:
    kind: str  # "turn_ok" / "turn_err" / "wake"


_KIND_COLORS = {
    "turn_ok": design.ACCENT_PRIMARY,
    "turn_err": design.ACCENT_WARM,
    "wake": design.ACCENT_OK,
}


class EventTimeline(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("hudPanel")
        self._events: deque[Event] = deque(maxlen=_CAPACITY)

        root = QVBoxLayout(self)
        root.setContentsMargins(
            design.SPACE_4, design.SPACE_3, design.SPACE_4, design.SPACE_3
        )
        root.setSpacing(design.SPACE_2)

        header = QLabel("EVENT TIMELINE")
        header.setProperty("role", "header")
        root.addWidget(header)

        self._ribbon = _Ribbon(self._events)
        root.addWidget(self._ribbon)

        legend = QLabel(
            f"<span style='color:{design.ACCENT_OK.hex}'>●</span> wake  "
            f"<span style='color:{design.ACCENT_PRIMARY.hex}'>●</span> turn  "
            f"<span style='color:{design.ACCENT_WARM.hex}'>●</span> error"
        )
        legend.setTextFormat(Qt.TextFormat.RichText)
        legend.setStyleSheet(
            f"""
            color: {design.TEXT_MUTED.hex};
            font-family: {design.FONT_UI};
            font-size: {design.FONT_SIZE_MICRO}px;
            letter-spacing: 2px;
            """
        )
        root.addWidget(legend)
        root.addStretch(1)

        self.setStyleSheet(
            f"""
            QFrame#hudPanel {{
                background-color: {design.SURFACE_CARD.rgba_css(0.55)};
                border: 1px solid {design.BORDER_SUBTLE.hex};
                border-radius: {design.RADIUS_MD}px;
            }}
            """
        )

    def record_turn(self, success: bool) -> None:
        self._append(Event(kind="turn_ok" if success else "turn_err"))

    def record_wake(self) -> None:
        self._append(Event(kind="wake"))

    def _append(self, event: Event) -> None:
        self._events.append(event)
        self._ribbon.update()


class _Ribbon(QWidget):
    """The actual painted strip of dots."""

    def __init__(self, events: deque[Event]) -> None:
        super().__init__()
        self.setFixedHeight(_DOT_SIZE + 12)
        self.setMinimumWidth(220)
        self._events = events

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = self.rect()
        painter.setPen(QPen(QColor(0, 240, 255, 25), 0.8))
        painter.drawLine(
            rect.left(), rect.center().y(), rect.right(), rect.center().y()
        )

        if not self._events:
            painter.setPen(QColor(design.TEXT_DIM.r, design.TEXT_DIM.g, design.TEXT_DIM.b))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "no activity yet")
            painter.end()
            return

        # Plot newest → oldest, right → left, so the latest event is
        # always under the user's eye on the right side.
        available = rect.width() - _DOT_SIZE
        cursor = rect.right() - _DOT_SIZE
        baseline = rect.center().y() - _DOT_SIZE / 2
        for event_obj in reversed(self._events):
            color = _KIND_COLORS.get(event_obj.kind, design.TEXT_MUTED)
            dot_rect = QRectF(cursor, baseline, _DOT_SIZE, _DOT_SIZE)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(color.r, color.g, color.b, 230)))
            painter.drawEllipse(dot_rect)
            cursor -= _DOT_SIZE + _DOT_SPACING
            if cursor < rect.left():
                break
        painter.end()
