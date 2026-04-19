"""Live clock for the HUD header — date + time + session uptime.

Ticks once a second; minimal enough not to compete with the rest of
the UI for attention, big enough to read at a glance.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class ClockWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("hudClock")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self._time_label = QLabel("--:--:--")
        self._time_label.setObjectName("clockTime")
        self._date_label = QLabel("-- --- ----")
        self._date_label.setObjectName("clockDate")

        layout.addWidget(self._time_label)
        layout.addWidget(self._date_label)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(500)  # 2Hz — cheap and catches seconds on time
        self._tick()

    def _tick(self) -> None:
        now = datetime.now()
        self._time_label.setText(now.strftime("%H:%M:%S"))
        self._date_label.setText(now.strftime("%a · %b %d · %Y").upper())
