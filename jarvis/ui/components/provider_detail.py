"""Full-height detail view for a provider.

Shown when the user clicks CONFIGURE on a ProviderCard. Presents:

    ← BACK          [Status badge]

    PROVIDER NAME
    Short tagline

    Long description paragraph
    ◆ Best for X
    "Usage example"

    API KEY  [input..............................] [Show]
    (when the provider needs a credential)

    OPEN PROVIDER SITE →

The detail view doesn't own credential state — it reads from and
writes to a shared credential bag passed by the host dialog, so
typing here updates the dialog's save payload without copy-pasting.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from jarvis.ui import design
from jarvis.ui.components.glow_frame import GlowFrame
from jarvis.ui.components.provider_card import ProviderOption
from jarvis.ui.components.status_badge import StatusBadge


class ProviderDetailPanel(QWidget):
    """Detail screen for a single provider. Owns only UI; credential
    read/write goes through the `get_credential` / `set_credential`
    callbacks the host wires up."""

    back_requested = Signal()

    def __init__(
        self,
        option: ProviderOption,
        get_credential: Callable[[str], str],
        set_credential: Callable[[str, str], None],
    ) -> None:
        super().__init__()
        self._option = option
        self._get_credential = get_credential
        self._set_credential = set_credential

        root = QVBoxLayout(self)
        root.setContentsMargins(
            design.SPACE_4, design.SPACE_4, design.SPACE_4, design.SPACE_4
        )
        root.setSpacing(design.SPACE_4)

        root.addLayout(self._build_header())

        # Body scrolls — long descriptions + credential form may exceed
        # tab height on smaller displays.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        body = GlowFrame(variant="card")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(
            design.SPACE_6, design.SPACE_5, design.SPACE_6, design.SPACE_5
        )
        body_layout.setSpacing(design.SPACE_4)

        body_layout.addWidget(self._build_name())
        body_layout.addWidget(self._build_tagline())
        body_layout.addWidget(self._build_description())
        body_layout.addWidget(self._build_strength())
        if option.example:
            body_layout.addWidget(self._build_example())

        if option.credential_key:
            body_layout.addSpacing(design.SPACE_3)
            body_layout.addLayout(self._build_credential_row())

        body_layout.addSpacing(design.SPACE_3)
        body_layout.addLayout(self._build_website_row())
        body_layout.addStretch(1)

        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    # ── header: back + badge ──────────────────────────────────────────

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(design.SPACE_3)
        back = QPushButton("← BACK TO LIST")
        back.setProperty("variant", "ghost")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self.back_requested.emit)
        row.addWidget(back)
        row.addStretch(1)

        badge = StatusBadge(
            state=self._option.status,
            text=self._option.status_text
            or self._option.status.upper().replace("_", " "),
        )
        row.addWidget(badge)
        return row

    # ── body blocks ──────────────────────────────────────────────────

    def _build_name(self) -> QLabel:
        label = QLabel(self._option.name)
        label.setStyleSheet(
            f"""
            color: {design.TEXT_PRIMARY.hex};
            font-family: {design.FONT_DISPLAY};
            font-size: 26px;
            font-weight: 700;
            letter-spacing: 4px;
            """
        )
        return label

    def _build_tagline(self) -> QLabel:
        label = QLabel(self._option.description)
        label.setWordWrap(True)
        label.setStyleSheet(
            f"""
            color: {design.TEXT_SECONDARY.hex};
            font-family: {design.FONT_UI};
            font-size: {design.FONT_SIZE_BODY}px;
            """
        )
        return label

    def _build_description(self) -> QLabel:
        # Long description falls back to the short one so the layout
        # still looks right on providers we haven't filled out deeply.
        text = self._option.long_description or self._option.description
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(
            f"""
            color: {design.TEXT_MUTED.hex};
            font-family: {design.FONT_UI};
            font-size: {design.FONT_SIZE_SMALL}px;
            line-height: 155%;
            """
        )
        return label

    def _build_strength(self) -> QLabel:
        label = QLabel(f"◆  {self._option.strength}")
        label.setStyleSheet(
            f"""
            color: {design.ACCENT_PRIMARY.rgba_css(0.9)};
            font-family: {design.FONT_UI};
            font-size: {design.FONT_SIZE_SMALL}px;
            letter-spacing: 2px;
            """
        )
        label.setWordWrap(True)
        return label

    def _build_example(self) -> QLabel:
        label = QLabel(f"“{self._option.example}”")
        label.setWordWrap(True)
        label.setStyleSheet(
            f"""
            color: {design.TEXT_MUTED.hex};
            font-family: {design.FONT_MONO};
            font-size: {design.FONT_SIZE_SMALL}px;
            font-style: italic;
            """
        )
        return label

    # ── credential row ────────────────────────────────────────────────

    def _build_credential_row(self) -> QVBoxLayout:
        section = QVBoxLayout()
        section.setSpacing(design.SPACE_2)

        header = QLabel(self._option.credential_label)
        header.setStyleSheet(
            f"""
            color: {design.ACCENT_PRIMARY.rgba_css(0.75)};
            font-family: {design.FONT_UI};
            font-size: {design.FONT_SIZE_MICRO}px;
            letter-spacing: 4px;
            """
        )
        section.addWidget(header)

        row = QHBoxLayout()
        row.setSpacing(design.SPACE_2)
        self._key_input = QLineEdit()
        self._key_input.setPlaceholderText(
            self._option.credential_placeholder or "API key"
        )
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        current = self._get_credential(self._option.credential_key or "")
        if current:
            self._key_input.setText(current)
        self._key_input.textChanged.connect(self._on_credential_changed)
        row.addWidget(self._key_input, 1)

        show = QCheckBox("SHOW")
        show.toggled.connect(
            lambda checked: self._key_input.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        row.addWidget(show)
        section.addLayout(row)

        hint = QLabel(
            "Stored locally in the OS keyring — never sent anywhere "
            "except the provider's API."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"""
            color: {design.TEXT_DIM.hex};
            font-family: {design.FONT_UI};
            font-size: {design.FONT_SIZE_MICRO}px;
            """
        )
        section.addWidget(hint)
        return section

    def _on_credential_changed(self, text: str) -> None:
        if self._option.credential_key:
            self._set_credential(self._option.credential_key, text.strip())

    # ── website link ──────────────────────────────────────────────────

    def _build_website_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(design.SPACE_2)
        if not self._option.website:
            return row
        site = QPushButton(f"OPEN {self._option.name.upper()} WEBSITE  →")
        site.setProperty("variant", "link")
        site.setCursor(Qt.CursorShape.PointingHandCursor)
        site.clicked.connect(
            lambda _=False: QDesktopServices.openUrl(QUrl(self._option.website))
        )
        row.addWidget(site, 1)
        return row
