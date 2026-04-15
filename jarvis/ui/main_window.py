from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from jarvis.config.strings import Strings
from jarvis.models.interaction_result import InteractionResult
from jarvis.ui.jarvis_orb import JarvisOrb


class MainWindow(QMainWindow):
    def __init__(self, strings: Strings) -> None:
        super().__init__()
        self._strings = strings
        self.setWindowTitle(strings.get("window_title"))
        self.setMinimumSize(880, 640)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._drag_origin: QPoint | None = None
        self._orb = JarvisOrb()
        self._build()
        self._apply_styles()

    def _build(self) -> None:
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(22, 22, 22, 22)

        frame = QWidget()
        frame.setObjectName("windowFrame")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(26, 18, 26, 26)
        frame_layout.setSpacing(0)

        top_bar = QHBoxLayout()
        top_bar.addStretch(1)
        close_button = QPushButton("×")
        close_button.setObjectName("closeButton")
        close_button.setFixedSize(32, 32)
        close_button.clicked.connect(self.close)
        top_bar.addWidget(close_button)
        frame_layout.addLayout(top_bar)

        center_container = QWidget()
        stack = QStackedLayout(center_container)
        stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        stack.setContentsMargins(0, 0, 0, 0)

        orb_holder = QWidget()
        orb_layout = QVBoxLayout(orb_holder)
        orb_layout.setContentsMargins(0, 0, 0, 0)
        orb_layout.addStretch(1)
        orb_layout.addWidget(self._orb, alignment=Qt.AlignmentFlag.AlignCenter)
        orb_layout.addStretch(1)

        text_holder = QWidget()
        text_holder.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        text_layout = QVBoxLayout(text_holder)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(10)
        text_layout.addStretch(1)

        self._title = QLabel(self._strings.get("title"))
        self._title.setObjectName("titleLabel")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._subtitle = QLabel(self._strings.get("subtitle"))
        self._subtitle.setObjectName("subtitleLabel")
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        text_layout.addWidget(self._title)
        text_layout.addWidget(self._subtitle)
        text_layout.addStretch(1)

        stack.addWidget(orb_holder)
        stack.addWidget(text_holder)

        frame_layout.addWidget(center_container, 1)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(44)
        shadow.setOffset(0, 0)
        shadow.setColor(QColor(0, 255, 255, 40))
        frame.setGraphicsEffect(shadow)

        outer_layout.addWidget(frame)
        self.setCentralWidget(outer)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background: transparent; }
            QWidget#windowFrame {
                background-color: rgba(8, 12, 16, 236);
                border: 1px solid rgba(0, 255, 255, 0.18);
                border-radius: 28px;
            }
            QLabel#titleLabel {
                color: #d7ffff;
                font-family: Bahnschrift;
                font-size: 72px;
                font-weight: 700;
                letter-spacing: 18px;
            }
            QLabel#subtitleLabel {
                color: rgba(125, 230, 240, 0.75);
                font-family: Bahnschrift;
                font-size: 14px;
                letter-spacing: 6px;
                text-transform: uppercase;
            }
            QPushButton#closeButton {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(0, 255, 255, 0.18);
                border-radius: 16px;
                color: #c9ffff;
                font-family: Consolas;
                font-size: 18px;
            }
            QPushButton#closeButton:hover { background-color: rgba(0, 255, 255, 0.18); }
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
        del status

    def update_transcript(self, transcript: str) -> None:
        del transcript

    def update_response(self, response: str) -> None:
        del response

    def display_result(self, result: InteractionResult) -> None:
        del result

    def set_speaking(self, speaking: bool) -> None:
        self._orb.set_speaking(speaking)
