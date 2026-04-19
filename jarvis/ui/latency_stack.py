"""Stacked latency bars — per-turn breakdown of STT / LLM / TTS time.

Replaces the plain total-only sparkline with a richer instrument: each
bar is segmented so you can see *where* the time went at a glance. Long
LLM stretches, for instance, stand out as a wide amber band even when
the total looks fine.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


@dataclass(frozen=True, slots=True)
class LatencyFrame:
    stt_ms: int
    llm_ms: int
    tts_ms: int

    @property
    def total(self) -> int:
        return self.stt_ms + self.llm_ms + self.tts_ms


# Latency bands share the HUD's cyan/amber/teal discipline: STT
# teal (healthy baseline), LLM amber (heaviest / warning tone), TTS
# paler cyan (secondary accent). No pink anywhere.
_STT_COLOR = QColor(61, 245, 194, 225)
_LLM_COLOR = QColor(255, 213, 107, 225)
_TTS_COLOR = QColor(110, 234, 255, 225)


class LatencyStack(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(96)
        self.setMinimumWidth(320)
        self._frames: tuple[LatencyFrame, ...] = ()

    def set_frames(self, frames: Sequence[LatencyFrame]) -> None:
        clean = tuple(
            LatencyFrame(max(0, f.stt_ms), max(0, f.llm_ms), max(0, f.tts_ms)) for f in frames
        )
        if clean == self._frames:
            return
        self._frames = clean
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = self.rect().adjusted(8, 14, -8, -18)
        painter.setPen(QPen(QColor(0, 255, 255, 35), 0.8))
        painter.drawRoundedRect(QRectF(rect), 5, 5)

        if not self._frames:
            painter.setPen(QColor(200, 230, 240, 120))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "awaiting first turn")
            self._draw_legend(painter, 0, 0)
            painter.end()
            return

        peak = max((f.total for f in self._frames), default=0) or 1
        count = len(self._frames)
        spacing = 2
        bar_w = max(3.0, (rect.width() - spacing * (count - 1)) / count)
        baseline = rect.bottom() - 2
        usable_h = rect.height() - 4

        for i, frame in enumerate(self._frames):
            x = rect.left() + i * (bar_w + spacing)
            y = baseline
            for part_ms, color in (
                (frame.stt_ms, _STT_COLOR),
                (frame.llm_ms, _LLM_COLOR),
                (frame.tts_ms, _TTS_COLOR),
            ):
                if part_ms <= 0:
                    continue
                h = usable_h * (part_ms / peak)
                segment = QRectF(x, y - h, bar_w, h)
                painter.setBrush(QBrush(color))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(segment, 1.5, 1.5)
                y -= h

        # Peak label top-right.
        painter.setPen(QColor(200, 230, 240, 180))
        painter.drawText(
            rect.adjusted(0, -12, -4, 0),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
            f"peak {peak} ms",
        )
        self._draw_legend(painter, rect.left(), rect.bottom() + 4)
        painter.end()

    def _draw_legend(self, painter: QPainter, x: float, y: float) -> None:
        # Inline legend below the chart — three coloured dots + labels.
        # Keeping it inside the widget avoids layout drift when the
        # panel resizes.
        entries = (
            ("STT", _STT_COLOR),
            ("LLM", _LLM_COLOR),
            ("TTS", _TTS_COLOR),
        )
        cursor_x = x
        radius = 4.0
        for label, color in entries:
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QRectF(cursor_x, y, radius * 2, radius * 2))
            painter.setPen(QColor(200, 230, 240, 200))
            painter.drawText(QRectF(cursor_x + radius * 2 + 4, y - 4, 36, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
            cursor_x += radius * 2 + 48
