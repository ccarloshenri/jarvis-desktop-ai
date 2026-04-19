"""Provider connection dashboard — a live list of every upstream
Jarvis depends on, each with a pulsing "live" indicator and a tiny
latency read-out. Fills the dead gap in the right column with
something a user can actually glance at and learn from.

The pulse is a purely decorative QTimer animation; the actual online
state is set externally via `set_service_state(name, state, detail)`.
Callers can leave the defaults alone — this widget works as a static
overview too.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from jarvis.ui import design


@dataclass
class _ServiceRow:
    key: str
    name: str
    state: str = "ready"  # "online" / "ready" / "offline" / "warn"
    detail: str = ""
    pulse_phase: float = 0.0


class _PulseDot(QWidget):
    """A small circle whose opacity drifts between 0.35 and 1.0, so
    "online" services read as alive rather than static."""

    def __init__(self, state: str = "ready") -> None:
        super().__init__()
        self.setFixedSize(14, 14)
        self._state = state
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)

    def set_state(self, state: str) -> None:
        if state == self._state:
            return
        self._state = state
        self.update()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.04) % 1.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        import math

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if self._state == "online":
            base = design.ACCENT_OK
            breath = 0.6 + 0.4 * (0.5 + 0.5 * math.sin(self._phase * 2 * math.pi))
        elif self._state == "ready":
            base = design.ACCENT_PRIMARY
            breath = 0.55
        elif self._state == "warn":
            base = design.ACCENT_WARM
            breath = 0.7 + 0.3 * (0.5 + 0.5 * math.sin(self._phase * 2 * math.pi))
        else:  # offline
            base = design.TEXT_MUTED
            breath = 0.45

        glow = QColor(base.r, base.g, base.b, int(60 * breath))
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(self.rect())

        inner = QRectF(3, 3, self.width() - 6, self.height() - 6)
        core = QColor(base.r, base.g, base.b, int(220 * breath))
        painter.setBrush(QBrush(core))
        painter.drawEllipse(inner)
        painter.end()


class ConnectionStatusPanel(QFrame):
    """Dashboard panel listing services and their live state."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("hudPanel")
        self._rows: dict[str, _ConnectionRow] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            design.SPACE_4, design.SPACE_3, design.SPACE_4, design.SPACE_3
        )
        layout.setSpacing(design.SPACE_2)

        header = QLabel("CONNECTIONS")
        header.setProperty("role", "header")
        layout.addWidget(header)

        # Default service roster — every subsystem the HUD actually
        # represents upstream. `set_service_state` can flip any of
        # these at runtime as credentials / backends come online.
        defaults = [
            ("llm", "AI BRAIN"),
            ("stt", "SPEECH → TEXT"),
            ("tts", "VOICE ENGINE"),
            ("wake", "WAKE WORD"),
            ("music", "MUSIC"),
        ]
        for key, name in defaults:
            row = _ConnectionRow(name)
            self._rows[key] = row
            layout.addWidget(row)
        layout.addStretch(1)

        self.setStyleSheet(
            f"""
            QFrame#hudPanel {{
                background-color: {design.SURFACE_CARD.rgba_css(0.55)};
                border: 1px solid {design.BORDER_SUBTLE.hex};
                border-radius: {design.RADIUS_MD}px;
            }}
            """
        )

    def set_service_state(
        self, key: str, state: str, detail: str = ""
    ) -> None:
        row = self._rows.get(key)
        if row is None:
            return
        row.set_state(state, detail)


class _ConnectionRow(QWidget):
    def __init__(self, name: str) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, design.SPACE_1, 0, design.SPACE_1)
        layout.setSpacing(design.SPACE_3)

        self._dot = _PulseDot()
        layout.addWidget(self._dot)

        self._name = QLabel(name)
        self._name.setStyleSheet(
            f"""
            color: {design.TEXT_SECONDARY.hex};
            font-family: {design.FONT_UI};
            font-size: {design.FONT_SIZE_MICRO}px;
            letter-spacing: 3px;
            """
        )
        layout.addWidget(self._name)
        layout.addStretch(1)

        self._detail = QLabel("—")
        self._detail.setStyleSheet(
            f"""
            color: {design.TEXT_MUTED.hex};
            font-family: {design.FONT_MONO};
            font-size: {design.FONT_SIZE_MICRO}px;
            """
        )
        layout.addWidget(self._detail)

    def set_state(self, state: str, detail: str) -> None:
        self._dot.set_state(state)
        self._detail.setText(detail or "—")
