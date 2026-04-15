from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedLayout,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from jarvis.config.strings import Strings
from jarvis.models.interaction_result import InteractionResult
from jarvis.services.update_checker import ReleaseInfo
from jarvis.ui.jarvis_orb import JarvisOrb


class MainWindow(QMainWindow):
    update_requested = Signal(object)
    settings_requested = Signal()

    def __init__(self, strings: Strings, debug: bool = False) -> None:
        super().__init__()
        self._strings = strings
        self._debug = debug
        self.setWindowTitle(strings.get("window_title"))
        self.setMinimumSize(880, 640)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._drag_origin: QPoint | None = None
        self._orb = JarvisOrb()
        self._debug_panel: QTextEdit | None = None
        self._update_banner: QFrame | None = None
        self._update_banner_label: QLabel | None = None
        self._pending_release: ReleaseInfo | None = None
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
        settings_button = QPushButton("⚙")
        settings_button.setObjectName("settingsButton")
        settings_button.setFixedSize(32, 32)
        settings_button.setToolTip("Configurações — trocar ou limpar IA")
        settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_button.clicked.connect(self.settings_requested.emit)
        top_bar.addWidget(settings_button)
        if self._debug:
            debug_badge = QLabel("DEBUG")
            debug_badge.setObjectName("debugBadge")
            top_bar.addWidget(debug_badge)
        top_bar.addStretch(1)
        close_button = QPushButton("×")
        close_button.setObjectName("closeButton")
        close_button.setFixedSize(32, 32)
        close_button.clicked.connect(self.close)
        top_bar.addWidget(close_button)
        frame_layout.addLayout(top_bar)

        self._update_banner = self._build_update_banner()
        frame_layout.addWidget(self._update_banner)

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

        if self._debug:
            self._debug_panel = QTextEdit()
            self._debug_panel.setObjectName("debugPanel")
            self._debug_panel.setReadOnly(True)
            self._debug_panel.setFixedHeight(140)
            frame_layout.addWidget(self._debug_panel)

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
            QLabel#debugBadge {
                color: #ff9bd3;
                background-color: rgba(255, 0, 130, 0.12);
                border: 1px solid rgba(255, 0, 130, 0.35);
                border-radius: 10px;
                padding: 4px 10px;
                font-family: Consolas;
                font-size: 11px;
                letter-spacing: 3px;
            }
            QTextEdit#debugPanel {
                background-color: rgba(4, 10, 14, 0.92);
                border: 1px solid rgba(0, 255, 255, 0.22);
                border-radius: 14px;
                color: #c9ffff;
                font-family: Consolas;
                font-size: 12px;
                padding: 10px 14px;
                selection-background-color: rgba(0, 255, 255, 0.28);
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
            QPushButton#settingsButton {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(0, 255, 255, 0.18);
                border-radius: 16px;
                color: #c9ffff;
                font-family: Segoe UI Symbol;
                font-size: 16px;
            }
            QPushButton#settingsButton:hover { background-color: rgba(0, 255, 255, 0.18); }
            QFrame#updateBanner {
                background-color: rgba(0, 255, 255, 0.08);
                border: 1px solid rgba(0, 255, 255, 0.35);
                border-radius: 14px;
                margin-top: 12px;
            }
            QLabel#updateBannerLabel {
                color: #d7ffff;
                font-family: Bahnschrift;
                font-size: 13px;
            }
            QPushButton#updateButton {
                background-color: rgba(0, 255, 255, 0.22);
                border: 1px solid rgba(0, 255, 255, 0.55);
                border-radius: 10px;
                color: #eafcff;
                padding: 6px 16px;
                font-family: Bahnschrift;
                font-size: 13px;
            }
            QPushButton#updateButton:hover { background-color: rgba(0, 255, 255, 0.38); }
            QPushButton#updateDismissButton {
                background-color: transparent;
                border: 1px solid rgba(0, 255, 255, 0.25);
                border-radius: 10px;
                color: rgba(215, 255, 255, 0.8);
                padding: 6px 12px;
                font-family: Bahnschrift;
                font-size: 12px;
            }
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
        if self._debug_panel is None or not transcript:
            return
        prefix = self._strings.get("debug_user_prefix")
        self._debug_panel.append(f"<span style='color:#9bffb8'>{prefix}:</span> {transcript}")

    def update_response(self, response: str) -> None:
        if self._debug_panel is None or not response:
            return
        prefix = self._strings.get("debug_jarvis_prefix")
        self._debug_panel.append(f"<span style='color:#8dfdff'>{prefix}:</span> {response}")

    def display_result(self, result: InteractionResult) -> None:
        del result

    def set_speaking(self, speaking: bool) -> None:
        self._orb.set_speaking(speaking)

    def _build_update_banner(self) -> QFrame:
        banner = QFrame()
        banner.setObjectName("updateBanner")
        banner.setVisible(False)
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        self._update_banner_label = QLabel("")
        self._update_banner_label.setObjectName("updateBannerLabel")
        self._update_banner_label.setWordWrap(True)
        layout.addWidget(self._update_banner_label, 1)

        update_button = QPushButton("Atualizar")
        update_button.setObjectName("updateButton")
        update_button.clicked.connect(self._on_update_clicked)
        layout.addWidget(update_button)

        dismiss_button = QPushButton("Depois")
        dismiss_button.setObjectName("updateDismissButton")
        dismiss_button.clicked.connect(self.hide_update_banner)
        layout.addWidget(dismiss_button)

        return banner

    def show_update_banner(self, release: ReleaseInfo) -> None:
        if self._update_banner is None or self._update_banner_label is None:
            return
        self._pending_release = release
        summary = (release.body or "").strip().splitlines()
        headline = summary[0] if summary else "Nova versão disponível."
        self._update_banner_label.setText(
            f"<b>Atualização disponível — v{release.version}</b><br/>{headline}"
        )
        self._update_banner.setVisible(True)

    def hide_update_banner(self) -> None:
        if self._update_banner is not None:
            self._update_banner.setVisible(False)

    def _on_update_clicked(self) -> None:
        if self._pending_release is not None:
            self.update_requested.emit(self._pending_release)
        self.hide_update_banner()
