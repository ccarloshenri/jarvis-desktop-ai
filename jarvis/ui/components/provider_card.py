"""Card widget for picking one provider (LLM / TTS / Music).

Layout (top to bottom):
    [NAME]                       [STATUS BADGE]
    [DESCRIPTION — 1–2 sentences]
    [STRENGTH TAG: "best for ..."]
    [EXAMPLE: "usage sample"]
    ───────────────────────────────
    [SELECT] [OPEN SITE →]

Emits `selected` when the user clicks Select. The dialog containing
the cards keeps track of which is active and flips variants via
`set_selected(bool)`.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.ui import design
from jarvis.ui.components.glow_frame import GlowFrame
from jarvis.ui.components.status_badge import StatusBadge


@dataclass(frozen=True, slots=True)
class ProviderOption:
    """Declarative definition of a provider option. Passed to
    ProviderCard as data — the card reads fields to render itself. No
    behaviour on this dataclass; all the interactive logic lives on
    the card widget."""

    key: str  # stable ID used by the host dialog ("openai", "groq", ...)
    name: str  # display name, correctly capitalised ("OpenAI", "Groq")
    description: str  # one or two sentences for the card listing
    strength: str  # "Best for X" short line
    example: str  # sample usage or voice
    website: str  # URL opened by the "Open site" button (detail view)
    status: str  # one of: active / ready / coming_soon / offline / error
    status_text: str = ""  # label shown inside the badge
    # Detail view extras.  `long_description` expands the summary with
    # more context, `credential_key` declares which API credential the
    # detail view should expose (e.g. "groq_api_key"), and
    # `credential_label` controls how the input is titled. None means
    # the provider needs no credentials and the detail view just
    # displays info + link.
    long_description: str = ""
    credential_key: str | None = None
    credential_label: str = "API KEY"
    credential_placeholder: str = ""


class ProviderCard(GlowFrame):
    """Compact card for the grid listing.

    Two buttons:
    - SELECT — marks this provider as the active choice without
      navigating away. Lets the user swap back to a no-config option
      (e.g. "Local Voice") in one click from anywhere in the grid.
    - CONFIGURE → — opens the detail view so the user can paste an
      API key or read the long-form description. Only shown for
      providers that declare a `credential_key`; keyless providers
      don't need a detail screen to be useful.
    """

    select_requested = Signal(str)  # user wants this provider active
    configure_requested = Signal(str)  # user wants the detail screen

    def __init__(self, option: ProviderOption) -> None:
        super().__init__(variant="card")
        self._option = option
        self._is_selected = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            design.SPACE_5, design.SPACE_4, design.SPACE_5, design.SPACE_4
        )
        layout.setSpacing(design.SPACE_3)

        layout.addLayout(self._build_header())
        layout.addWidget(self._build_description())
        layout.addWidget(self._build_strength())
        if option.example:
            layout.addWidget(self._build_example())
        layout.addStretch(1)
        layout.addLayout(self._build_actions())

        # If the option shipped as "coming_soon" or "offline", the
        # card should read as unavailable from first paint.
        if option.status in {"coming_soon", "offline"}:
            self.set_variant("disabled")
            self._select_button.setEnabled(False)
            if self._configure_button is not None:
                self._configure_button.setEnabled(False)

    # ── public API ────────────────────────────────────────────────────

    @property
    def option(self) -> ProviderOption:
        return self._option

    def set_selected(self, selected: bool) -> None:
        if selected == self._is_selected:
            return
        self._is_selected = selected
        self.set_variant("selected" if selected else "card")
        if selected:
            self._badge.set_state("active", "ACTIVE")
            self._select_button.setText("✓  SELECTED")
        else:
            self._badge.set_state(
                self._option.status,
                self._option.status_text or self._option.status.upper().replace("_", " "),
            )
            self._select_button.setText("SELECT")
        # Leave both buttons clickable whenever the provider is
        # actually available — even when already selected, so the
        # user can re-open the configure sheet to edit a key. Only
        # unavailable (coming_soon / offline) providers stay disabled.
        enabled = self._option.status not in {"coming_soon", "offline"}
        self._select_button.setEnabled(enabled)
        if self._configure_button is not None:
            self._configure_button.setEnabled(enabled)

    # ── build helpers ─────────────────────────────────────────────────

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(design.SPACE_3)
        name = QLabel(self._option.name)
        name.setProperty("role", "title")
        row.addWidget(name)
        row.addStretch(1)
        self._badge = StatusBadge(
            state=self._option.status,
            text=self._option.status_text
            or self._option.status.upper().replace("_", " "),
        )
        row.addWidget(self._badge)
        return row

    def _build_description(self) -> QLabel:
        label = QLabel(self._option.description)
        label.setProperty("role", "muted")
        label.setWordWrap(True)
        label.setStyleSheet(
            f"color: {design.TEXT_SECONDARY.hex}; font-size: {design.FONT_SIZE_BODY}px;"
        )
        return label

    def _build_strength(self) -> QLabel:
        label = QLabel(f"◆  {self._option.strength}")
        label.setWordWrap(True)
        label.setStyleSheet(
            f"""
            color: {design.ACCENT_PRIMARY.rgba_css(0.9)};
            font-family: {design.FONT_UI};
            font-size: {design.FONT_SIZE_SMALL}px;
            letter-spacing: 1px;
            """
        )
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

    def _build_actions(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, design.SPACE_2, 0, 0)
        row.setSpacing(design.SPACE_2)

        self._select_button = QPushButton("SELECT")
        self._select_button.setProperty("variant", "primary")
        self._select_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._select_button.clicked.connect(
            lambda: self.select_requested.emit(self._option.key)
        )
        row.addWidget(self._select_button)

        self._configure_button: QPushButton | None = None
        # Only providers that carry a credential need a dedicated
        # configure path. A keyless provider (e.g. Local Voice) is
        # fully usable with just SELECT, and a CONFIGURE button with
        # nothing to configure is noise.
        if self._option.credential_key:
            self._configure_button = QPushButton("CONFIGURE")
            self._configure_button.setProperty("variant", "ghost")
            self._configure_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self._configure_button.clicked.connect(
                lambda: self.configure_requested.emit(self._option.key)
            )
            row.addWidget(self._configure_button)
        row.addStretch(1)
        return row
