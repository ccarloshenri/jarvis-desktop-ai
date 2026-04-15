from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QPoint, QUrl, Qt
from PySide6.QtGui import QColor, QDesktopServices, QMouseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from jarvis.enums.llm_provider import LLMProvider

LOGGER = logging.getLogger(__name__)


TestResult = tuple[bool, str]
TestFunction = Callable[[str], TestResult]


@dataclass(frozen=True)
class ProviderOption:
    provider: LLMProvider
    name: str
    tagline: str
    description: str
    url: str
    url_label: str
    key_hint: str
    requires_key: bool
    tester: TestFunction | None


@dataclass(frozen=True)
class ProviderChoice:
    provider: LLMProvider
    api_key: str


def _test_openai(api_key: str) -> TestResult:
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        client.models.list()
        return True, "Conectado com sucesso."
    except Exception as exc:
        return False, str(exc)


def _test_gemini(api_key: str) -> TestResult:
    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        list(genai.list_models())
        return True, "Conectado com sucesso."
    except Exception as exc:
        return False, str(exc)


def _test_anthropic(api_key: str) -> TestResult:
    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=api_key)
        client.messages.create(
            model="claude-3-5-haiku-latest",
            max_tokens=1,
            messages=[{"role": "user", "content": "ok"}],
        )
        return True, "Conectado com sucesso."
    except Exception as exc:
        return False, str(exc)


PROVIDER_OPTIONS: tuple[ProviderOption, ...] = (
    ProviderOption(
        provider=LLMProvider.GPT,
        name="OpenAI GPT",
        tagline="Recomendado",
        description="Usa GPT-4o mini via API da OpenAI. Rápido e preciso.",
        url="https://platform.openai.com/api-keys",
        url_label="Obter chave de API",
        key_hint="sk-...",
        requires_key=True,
        tester=_test_openai,
    ),
    ProviderOption(
        provider=LLMProvider.GEMINI,
        name="Google Gemini",
        tagline="Free tier generoso",
        description="Usa Gemini 1.5 Flash via Google AI Studio.",
        url="https://aistudio.google.com/apikey",
        url_label="Obter chave de API",
        key_hint="AIza...",
        requires_key=True,
        tester=_test_gemini,
    ),
    ProviderOption(
        provider=LLMProvider.CLAUDE,
        name="Anthropic Claude",
        tagline="Conversacional",
        description="Usa Claude 3.5 Haiku via console da Anthropic.",
        url="https://console.anthropic.com/settings/keys",
        url_label="Obter chave de API",
        key_hint="sk-ant-...",
        requires_key=True,
        tester=_test_anthropic,
    ),
    ProviderOption(
        provider=LLMProvider.NONE,
        name="Modo Offline",
        tagline="Sem internet",
        description="Respostas básicas, sem IA remota. Comandos por regras continuam funcionando.",
        url="",
        url_label="",
        key_hint="",
        requires_key=False,
        tester=None,
    ),
)


class _ProviderCard(QFrame):
    def __init__(self, option: ProviderOption, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.option = option
        self.setObjectName("providerCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._selected = False
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)

        name = QLabel(self.option.name)
        name.setObjectName("providerName")
        header.addWidget(name)
        header.addStretch(1)

        if self.option.tagline:
            tag = QLabel(self.option.tagline.upper())
            tag.setObjectName("providerTag")
            header.addWidget(tag)

        layout.addLayout(header)

        description = QLabel(self.option.description)
        description.setObjectName("providerDescription")
        description.setWordWrap(True)
        layout.addWidget(description)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked()
        super().mousePressEvent(event)

    def clicked(self) -> None:  # overridden via attribute
        pass


class ProviderSetupDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        initial_provider: LLMProvider | None = None,
        existing_keys: dict[LLMProvider, str] | None = None,
    ) -> None:
        super().__init__(parent)
        self._existing_keys = existing_keys or {}
        self._choice: ProviderChoice | None = None
        self._cards: dict[LLMProvider, _ProviderCard] = {}
        self._inputs: dict[LLMProvider, QLineEdit] = {}
        self._status_labels: dict[LLMProvider, QLabel] = {}
        self._option_by_provider = {opt.provider: opt for opt in PROVIDER_OPTIONS}
        self._drag_origin: QPoint | None = None

        self.setWindowTitle("Jarvis — Inicialização")
        self.setModal(True)
        self.setFixedSize(720, 720)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._build()
        self._apply_styles()
        self._select_provider(initial_provider or LLMProvider.GPT, focus_input=False)

    @property
    def choice(self) -> ProviderChoice | None:
        return self._choice

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 22, 22, 22)

        self._frame = QFrame()
        self._frame.setObjectName("dialogFrame")
        root = QVBoxLayout(self._frame)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(18)

        top = QHBoxLayout()
        title = QLabel("ESCOLHA A INTELIGÊNCIA")
        title.setObjectName("dialogTitle")
        top.addWidget(title)
        top.addStretch(1)
        close_button = QPushButton("×")
        close_button.setObjectName("closeButton")
        close_button.setFixedSize(32, 32)
        close_button.clicked.connect(self.reject)
        top.addWidget(close_button)
        root.addLayout(top)

        subtitle = QLabel("Selecione qual IA o Jarvis vai usar para entender e responder.")
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        cards_grid = QGridLayout()
        cards_grid.setSpacing(14)
        cards_grid.setHorizontalSpacing(14)
        cards_grid.setVerticalSpacing(14)
        for index, option in enumerate(PROVIDER_OPTIONS):
            card = _ProviderCard(option)
            card.clicked = lambda provider=option.provider: self._select_provider(provider)  # type: ignore[method-assign]
            self._cards[option.provider] = card
            row, col = divmod(index, 2)
            cards_grid.addWidget(card, row, col)
        cards_grid.setColumnStretch(0, 1)
        cards_grid.setColumnStretch(1, 1)
        root.addLayout(cards_grid)

        self._stack = QStackedWidget()
        for option in PROVIDER_OPTIONS:
            self._stack.addWidget(self._build_panel(option))
        root.addWidget(self._stack, 1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        cancel = QPushButton("Cancelar")
        cancel.setObjectName("secondaryButton")
        cancel.clicked.connect(self.reject)
        bottom.addWidget(cancel)

        self._save_button = QPushButton("Salvar e conectar")
        self._save_button.setObjectName("primaryButton")
        self._save_button.setDefault(True)
        self._save_button.clicked.connect(self._on_save_clicked)
        bottom.addWidget(self._save_button)
        root.addLayout(bottom)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(44)
        shadow.setOffset(0, 0)
        shadow.setColor(QColor(0, 255, 255, 50))
        self._frame.setGraphicsEffect(shadow)

        outer.addWidget(self._frame)

    def _build_panel(self, option: ProviderOption) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)

        if not option.requires_key:
            info = QLabel(
                "<b>Modo offline.</b> O Jarvis responde com um fallback básico "
                "e continua executando comandos por regras (abrir apps, Spotify, "
                "pesquisa). Nenhuma chave necessária."
            )
            info.setObjectName("panelInfo")
            info.setWordWrap(True)
            layout.addWidget(info)
            layout.addStretch(1)
            return panel

        instruction = QLabel(
            f"Clique em <b>{option.url_label}</b>, gere uma chave no site do provedor "
            "e cole aqui. Ela será salva com segurança no Gerenciador de Credenciais "
            "do Windows."
        )
        instruction.setObjectName("panelInfo")
        instruction.setWordWrap(True)
        layout.addWidget(instruction)

        url_button = QPushButton(option.url_label)
        url_button.setObjectName("linkButton")
        url_button.clicked.connect(lambda _=False, url=option.url: QDesktopServices.openUrl(QUrl(url)))
        layout.addWidget(url_button)

        row = QHBoxLayout()
        row.setSpacing(8)

        key_input = QLineEdit()
        key_input.setObjectName("keyInput")
        key_input.setEchoMode(QLineEdit.EchoMode.Password)
        key_input.setPlaceholderText(option.key_hint)
        if option.provider in self._existing_keys:
            key_input.setText(self._existing_keys[option.provider])
        key_input.textChanged.connect(lambda _=None, p=option.provider: self._on_key_changed(p))
        row.addWidget(key_input, 1)
        self._inputs[option.provider] = key_input

        show_box = QCheckBox("Mostrar")
        show_box.setObjectName("showCheckbox")
        show_box.toggled.connect(
            lambda checked, field=key_input: field.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        row.addWidget(show_box)

        test_button = QPushButton("Testar")
        test_button.setObjectName("secondaryButton")
        test_button.clicked.connect(lambda _=False, p=option.provider: self._on_test_clicked(p))
        row.addWidget(test_button)

        layout.addLayout(row)

        status = QLabel("")
        status.setObjectName("statusLabel")
        status.setWordWrap(True)
        status.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(status)
        self._status_labels[option.provider] = status

        layout.addStretch(1)
        return panel

    def _select_provider(self, provider: LLMProvider, focus_input: bool = True) -> None:
        for p, card in self._cards.items():
            card.set_selected(p == provider)
        self._stack.setCurrentIndex(self._provider_index(provider))
        self._current_provider = provider
        if focus_input and provider in self._inputs:
            self._inputs[provider].setFocus()
        self._update_save_button()

    def _provider_index(self, provider: LLMProvider) -> int:
        for index, option in enumerate(PROVIDER_OPTIONS):
            if option.provider == provider:
                return index
        return 0

    def _on_key_changed(self, provider: LLMProvider) -> None:
        self._status_labels[provider].setText("")
        self._update_save_button()

    def _update_save_button(self) -> None:
        option = self._option_by_provider[self._current_provider]
        if not option.requires_key:
            self._save_button.setEnabled(True)
            return
        key = self._inputs[option.provider].text().strip()
        self._save_button.setEnabled(bool(key))

    def _on_test_clicked(self, provider: LLMProvider) -> None:
        option = self._option_by_provider[provider]
        if option.tester is None:
            return
        key = self._inputs[provider].text().strip()
        if not key:
            return
        status = self._status_labels[provider]
        status.setText("<span style='color:#9ae8ff;'>Testando conexão...</span>")
        status.repaint()
        success, message = option.tester(key)
        color = "#2ecc71" if success else "#ff6f8b"
        symbol = "✓" if success else "✗"
        status.setText(f"<span style='color:{color};'>{symbol} {message}</span>")

    def _on_save_clicked(self) -> None:
        option = self._option_by_provider[self._current_provider]
        if not option.requires_key:
            self._choice = ProviderChoice(provider=option.provider, api_key="")
            self.accept()
            return

        key = self._inputs[option.provider].text().strip()
        if not key:
            return
        status = self._status_labels[option.provider]
        if option.tester is not None:
            status.setText("<span style='color:#9ae8ff;'>Testando conexão...</span>")
            status.repaint()
            success, message = option.tester(key)
            if not success:
                status.setText(f"<span style='color:#ff6f8b;'>✗ {message}</span>")
                return
            status.setText(f"<span style='color:#2ecc71;'>✓ {message}</span>")
        self._choice = ProviderChoice(provider=option.provider, api_key=key)
        self.accept()

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

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QDialog { background: transparent; }
            QFrame#dialogFrame {
                background-color: rgba(8, 12, 16, 244);
                border: 1px solid rgba(0, 255, 255, 0.22);
                border-radius: 24px;
            }
            QLabel#dialogTitle {
                color: #d7ffff;
                font-family: Bahnschrift;
                font-size: 22px;
                font-weight: 700;
                letter-spacing: 5px;
            }
            QLabel#dialogSubtitle {
                color: rgba(210, 240, 255, 0.72);
                font-family: Bahnschrift;
                font-size: 13px;
                letter-spacing: 1px;
            }
            QLabel#panelInfo {
                color: rgba(215, 255, 255, 0.82);
                font-family: Bahnschrift;
                font-size: 13px;
            }
            QLabel#statusLabel {
                font-family: Consolas;
                font-size: 12px;
                min-height: 18px;
            }
            QFrame#providerCard {
                background-color: rgba(10, 22, 30, 0.72);
                border: 1px solid rgba(0, 255, 255, 0.18);
                border-radius: 14px;
            }
            QFrame#providerCard:hover {
                background-color: rgba(0, 255, 255, 0.08);
                border: 1px solid rgba(0, 255, 255, 0.35);
            }
            QFrame#providerCard[selected="true"] {
                background-color: rgba(0, 255, 255, 0.14);
                border: 1px solid rgba(0, 255, 255, 0.75);
            }
            QLabel#providerName {
                color: #d7ffff;
                font-family: Bahnschrift;
                font-size: 14px;
                font-weight: 700;
                letter-spacing: 1px;
            }
            QLabel#providerTag {
                color: #0a1016;
                background-color: rgba(0, 255, 255, 0.75);
                font-family: Consolas;
                font-size: 9px;
                letter-spacing: 1px;
                border-radius: 6px;
                padding: 2px 6px;
            }
            QLabel#providerDescription {
                color: rgba(200, 230, 240, 0.72);
                font-family: Bahnschrift;
                font-size: 11px;
            }
            QLineEdit#keyInput {
                background-color: rgba(4, 10, 14, 0.92);
                border: 1px solid rgba(0, 255, 255, 0.28);
                border-radius: 10px;
                color: #eafcff;
                font-family: Consolas;
                font-size: 13px;
                padding: 8px 12px;
                selection-background-color: rgba(0, 255, 255, 0.28);
            }
            QLineEdit#keyInput:focus {
                border: 1px solid rgba(0, 255, 255, 0.65);
            }
            QCheckBox#showCheckbox {
                color: rgba(210, 240, 255, 0.72);
                font-family: Bahnschrift;
                font-size: 12px;
            }
            QPushButton#primaryButton {
                background-color: rgba(0, 255, 255, 0.22);
                border: 1px solid rgba(0, 255, 255, 0.55);
                border-radius: 12px;
                color: #eafcff;
                padding: 9px 22px;
                font-family: Bahnschrift;
                font-size: 13px;
                letter-spacing: 1px;
            }
            QPushButton#primaryButton:hover { background-color: rgba(0, 255, 255, 0.38); }
            QPushButton#primaryButton:disabled {
                color: rgba(215, 255, 255, 0.3);
                background-color: rgba(0, 255, 255, 0.06);
                border: 1px solid rgba(0, 255, 255, 0.18);
            }
            QPushButton#secondaryButton {
                background-color: transparent;
                border: 1px solid rgba(0, 255, 255, 0.3);
                border-radius: 12px;
                color: #c9ffff;
                padding: 9px 18px;
                font-family: Bahnschrift;
                font-size: 13px;
                letter-spacing: 1px;
            }
            QPushButton#secondaryButton:hover {
                background-color: rgba(0, 255, 255, 0.12);
                border: 1px solid rgba(0, 255, 255, 0.55);
            }
            QPushButton#linkButton {
                background-color: rgba(0, 255, 255, 0.08);
                border: 1px dashed rgba(0, 255, 255, 0.45);
                border-radius: 10px;
                color: #9ae8ff;
                padding: 8px 14px;
                font-family: Bahnschrift;
                font-size: 12px;
                text-align: left;
            }
            QPushButton#linkButton:hover {
                background-color: rgba(0, 255, 255, 0.18);
                color: #eafcff;
            }
            QPushButton#closeButton {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(0, 255, 255, 0.22);
                border-radius: 16px;
                color: #c9ffff;
                font-family: Consolas;
                font-size: 18px;
            }
            QPushButton#closeButton:hover { background-color: rgba(0, 255, 255, 0.22); }
            """
        )
