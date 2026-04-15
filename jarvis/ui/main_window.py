from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget

from jarvis.models.interaction_result import InteractionResult
from jarvis.ui.jarvis_orb import JarvisOrb


class MainWindow(QMainWindow):
    def __init__(self, asset_path: Path) -> None:
        super().__init__()
        self.setWindowTitle("Jarvis Desktop AI")
        self.setMinimumSize(980, 720)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._drag_origin: QPoint | None = None
        self._orb = JarvisOrb(asset_path=asset_path)
        self._build()
        self._apply_styles()

    def _build(self) -> None:
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(22, 22, 22, 22)
        frame = QWidget()
        frame.setObjectName("windowFrame")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(26, 24, 26, 24)
        frame_layout.setSpacing(20)
        header_layout = QHBoxLayout()
        self._title = QLabel("JARVIS")
        self._title.setObjectName("titleLabel")
        self._status = QLabel("Status: Booting")
        self._status.setObjectName("statusLabel")
        close_button = QPushButton("x")
        close_button.setObjectName("closeButton")
        close_button.setFixedSize(32, 32)
        close_button.clicked.connect(self.close)
        header_layout.addWidget(self._title)
        header_layout.addStretch(1)
        header_layout.addWidget(self._status)
        header_layout.addWidget(close_button)
        self._response = QLabel("System online.")
        self._response.setObjectName("responseLabel")
        self._response.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._transcript = QTextEdit()
        self._transcript.setReadOnly(True)
        self._transcript.setPlaceholderText("Awaiting voice commands...")
        self._transcript.setObjectName("transcriptPanel")
        frame_layout.addLayout(header_layout)
        frame_layout.addWidget(self._orb, alignment=Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(self._response)
        frame_layout.addWidget(self._transcript)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 0)
        shadow.setColor(QColor(0, 255, 255, 36))
        frame.setGraphicsEffect(shadow)
        outer_layout.addWidget(frame)
        self.setCentralWidget(outer)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background: transparent; }
            QWidget#windowFrame { background-color: rgba(10, 10, 10, 232); border: 1px solid rgba(0, 255, 255, 0.18); border-radius: 28px; }
            QLabel { color: #c9ffff; }
            QLabel#titleLabel { font-family: Bahnschrift; font-size: 34px; font-weight: 700; letter-spacing: 7px; }
            QLabel#statusLabel { background-color: rgba(0, 255, 255, 0.08); border: 1px solid rgba(0, 255, 255, 0.22); border-radius: 16px; color: #7efcff; padding: 8px 14px; font-family: Consolas; font-size: 12px; }
            QLabel#responseLabel { color: #8dfdff; font-family: Bahnschrift; font-size: 18px; padding: 6px; }
            QTextEdit#transcriptPanel { background-color: rgba(6, 16, 16, 0.88); border: 1px solid rgba(0, 255, 255, 0.28); border-radius: 18px; color: #d8ffff; font-family: Consolas; font-size: 14px; padding: 14px; selection-background-color: rgba(0, 255, 255, 0.28); }
            QPushButton#closeButton { background-color: rgba(255, 255, 255, 0.06); border: 1px solid rgba(0, 255, 255, 0.18); border-radius: 16px; color: #c9ffff; font-family: Consolas; font-size: 14px; }
            QPushButton#closeButton:hover { background-color: rgba(0, 255, 255, 0.16); }
            """
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_origin)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_origin = None
        super().mouseReleaseEvent(event)

    def update_status(self, status: str) -> None:
        self._status.setText(f"Status: {status}")

    def update_transcript(self, transcript: str) -> None:
        self._transcript.append(f"> {transcript}")

    def update_response(self, response: str) -> None:
        self._response.setText(response)

    def display_result(self, result: InteractionResult) -> None:
        if result.command and result.action_result:
            self._transcript.append(
                f"[{result.command.action.value}] {result.command.target} -> {result.action_result.message}"
            )

    def set_speaking(self, speaking: bool) -> None:
        self._orb.set_speaking(speaking)
