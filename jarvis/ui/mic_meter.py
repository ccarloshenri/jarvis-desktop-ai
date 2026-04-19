"""Live VU meter for the captured mic signal.

Draws a segmented bar in the Jarvis cyan palette. The target level comes
from the audio capture thread via event_bus.mic_level_changed and feeds
a smoothing filter — raw RMS is jumpy enough at 12Hz that the bar would
flicker without a slight fall-off and rise easing.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget


_SEGMENTS = 28
_SEGMENT_SPACING = 3
_REPAINT_INTERVAL_MS = 33  # ~30 FPS


class MicLevelMeter(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(28)
        self.setMinimumWidth(220)
        # Separate `target` and `display` values so we can ease between
        # jumpy audio readings. target jumps; display chases it.
        self._target_level = 0.0
        self._display_level = 0.0
        self._peak_level = 0.0
        self._peak_hold_frames = 0

        # Repaint timer eases the display value toward the target and
        # decays the peak marker independently of the producer rate.
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(_REPAINT_INTERVAL_MS)

    def set_level(self, level: float) -> None:
        """Feed a new audio level into the meter (0..1, clamped)."""
        self._target_level = max(0.0, min(1.0, float(level)))
        if self._target_level > self._peak_level:
            self._peak_level = self._target_level
            self._peak_hold_frames = 20

    def _tick(self) -> None:
        # Rise quickly toward the target, fall off slowly. Matches how
        # pro-audio meters feel: snappy on attack, lazy on release.
        if self._target_level > self._display_level:
            self._display_level += (self._target_level - self._display_level) * 0.55
        else:
            self._display_level += (self._target_level - self._display_level) * 0.18

        if self._peak_hold_frames > 0:
            self._peak_hold_frames -= 1
        else:
            self._peak_level *= 0.95  # decay after hold
            if self._peak_level < 0.02:
                self._peak_level = 0.0

        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802  (Qt API name)
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))

        width = self.width()
        height = self.height()
        total_spacing = _SEGMENT_SPACING * (_SEGMENTS - 1)
        segment_width = max(1.0, (width - total_spacing) / _SEGMENTS)
        lit = int(self._display_level * _SEGMENTS)
        peak_idx = int(self._peak_level * _SEGMENTS) - 1

        for i in range(_SEGMENTS):
            x = i * (segment_width + _SEGMENT_SPACING)
            rect = QRectF(x, 2, segment_width, height - 4)
            if i < lit:
                # Colour ramp: cyan → paler cyan → amber near the top.
                # Amber at the hot end still signals "loud" without
                # the magenta that used to look out of place against
                # the rest of the HUD palette.
                ratio = i / _SEGMENTS
                if ratio < 0.55:
                    color = QColor(0, 240, 255, 220)
                elif ratio < 0.8:
                    color = QColor(110, 234, 255, 220)
                else:
                    color = QColor(255, 213, 107, 230)
                painter.setBrush(QBrush(color))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(rect, 2, 2)
            elif i == peak_idx:
                painter.setBrush(QBrush(QColor(0, 255, 255, 150)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(rect, 2, 2)
            else:
                painter.setBrush(QBrush(QColor(0, 255, 255, 25)))
                painter.setPen(QPen(QColor(0, 255, 255, 45), 0.6))
                painter.drawRoundedRect(rect, 2, 2)

        painter.end()

    # Unused helper kept in case the gradient renders better than
    # per-segment colours on some monitors — referenced from paintEvent
    # experiments during tuning.
    @staticmethod
    def _ramp_gradient(rect: QRectF) -> QLinearGradient:
        gradient = QLinearGradient(rect.left(), 0, rect.right(), 0)
        gradient.setColorAt(0.0, QColor(0, 240, 255))
        gradient.setColorAt(0.5, QColor(110, 234, 255))
        gradient.setColorAt(1.0, QColor(255, 213, 107))
        return gradient
