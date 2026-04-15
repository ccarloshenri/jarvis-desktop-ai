from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget

from jarvis.ui.orb_animation_state import OrbAnimationState


class JarvisOrb(QWidget):
    def __init__(self, asset_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(360, 360)
        self._asset = QPixmap(str(asset_path))
        self._state = OrbAnimationState()
        self._start_time = time.perf_counter()
        self._last_tick = self._start_time
        self._activity_level = 0.0
        self._activity_animation = QPropertyAnimation(self, b"activityLevel")
        self._activity_animation.setDuration(280)
        self._activity_animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def get_activity_level(self) -> float:
        return self._activity_level

    def set_activity_level(self, value: float) -> None:
        self._activity_level = max(0.0, min(1.0, value))
        self.update()

    activityLevel = Property(float, get_activity_level, set_activity_level)

    def set_speaking(self, speaking: bool) -> None:
        self._state.set_speaking(speaking)
        self._activity_animation.stop()
        self._activity_animation.setStartValue(self._activity_level)
        self._activity_animation.setEndValue(1.0 if speaking else 0.0)
        self._activity_animation.start()

    def _tick(self) -> None:
        now = time.perf_counter()
        self._state.advance(now - self._last_tick)
        self._last_tick = now
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        elapsed = time.perf_counter() - self._start_time
        frame = self._state.sample(elapsed)
        center_x = self.width() / 2
        center_y = self.height() / 2
        radius = frame.radius + self._activity_level * 8.0
        self._paint_glow(painter, center_x, center_y, frame.glow_radius + self._activity_level * 22.0)
        self._paint_rings(painter, center_x, center_y, radius, frame.ring_offset)
        self._paint_rotating_arcs(painter, center_x, center_y, radius + 28.0, frame.arc_rotation)
        self._paint_core(painter, center_x, center_y, radius, frame.core_opacity)
        self._paint_asset(painter, center_x, center_y, radius)

    def _paint_glow(self, painter: QPainter, center_x: float, center_y: float, glow_radius: float) -> None:
        gradient = QRadialGradient(center_x, center_y, glow_radius)
        gradient.setColorAt(0.0, QColor(0, 255, 255, 85 + int(self._activity_level * 70)))
        gradient.setColorAt(0.45, QColor(0, 255, 255, 36 + int(self._activity_level * 48)))
        gradient.setColorAt(1.0, QColor(0, 255, 255, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(QRectF(center_x - glow_radius, center_y - glow_radius, glow_radius * 2, glow_radius * 2))

    def _paint_rings(self, painter: QPainter, center_x: float, center_y: float, radius: float, ring_offset: float) -> None:
        ring_colors = [QColor(0, 255, 255, 190), QColor(110, 246, 255, 120), QColor(0, 255, 255, 60)]
        for index, color in enumerate(ring_colors):
            current_radius = radius + index * ring_offset
            painter.setPen(QPen(color, 2 if index == 0 else 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(center_x - current_radius, center_y - current_radius, current_radius * 2, current_radius * 2))

    def _paint_rotating_arcs(self, painter: QPainter, center_x: float, center_y: float, radius: float, rotation: float) -> None:
        painter.save()
        painter.translate(center_x, center_y)
        painter.rotate(rotation)
        painter.translate(-center_x, -center_y)
        arc_rect = QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(0, 255, 255, 220), 4))
        painter.drawArc(arc_rect, 0, 70 * 16)
        painter.drawArc(arc_rect, 180 * 16, 58 * 16)
        painter.setPen(QPen(QColor(0, 255, 255, 110), 2))
        painter.drawArc(arc_rect.adjusted(-10, -10, 10, 10), 100 * 16, 42 * 16)
        painter.drawArc(arc_rect.adjusted(12, 12, -12, -12), 255 * 16, 36 * 16)
        painter.restore()

    def _paint_core(self, painter: QPainter, center_x: float, center_y: float, radius: float, core_opacity: float) -> None:
        gradient = QRadialGradient(center_x, center_y, radius)
        gradient.setColorAt(0.0, QColor(150, 255, 255, int(core_opacity * 255)))
        gradient.setColorAt(0.45, QColor(0, 255, 255, 90 + int(self._activity_level * 70)))
        gradient.setColorAt(1.0, QColor(0, 160, 190, 18))
        painter.setPen(QPen(QColor(170, 255, 255, 220), 2))
        painter.setBrush(gradient)
        painter.drawEllipse(QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2))
        painter.setPen(QPen(QColor(200, 255, 255, 100 + int(self._activity_level * 100)), 1))
        for index in range(3):
            offset = (index + 1) * 10
            painter.drawEllipse(
                QRectF(center_x - radius + offset, center_y - radius + offset, (radius - offset) * 2, (radius - offset) * 2)
            )

    def _paint_asset(self, painter: QPainter, center_x: float, center_y: float, radius: float) -> None:
        if self._asset.isNull():
            painter.setPen(QColor("#C7FFFF"))
            painter.drawText(QRectF(center_x - radius, center_y - 18, radius * 2, 36), Qt.AlignmentFlag.AlignCenter, "JARVIS")
            return
        asset_size = max(84, min(160, int(radius * 1.05)))
        painter.setOpacity(0.78 + self._activity_level * 0.18)
        painter.drawPixmap(QRectF(center_x - asset_size / 2, center_y - asset_size / 2, asset_size, asset_size).toRect(), self._asset)
        painter.setOpacity(1.0)
