"""Jarvis Settings — a three-tab dialog wrapping every provider choice
the assistant exposes.

Tabs (left to right, priority-ordered by how often the user touches
them):
    1. Intelligence — LLM provider (OpenAI, Gemini, Groq, Anthropic, Local)
    2. Voice         — TTS engine (ElevenLabs, Groq, Streamlabs, Local)
    3. Music         — Music provider (Spotify, SoundCloud)

Each tab is a two-page stack: a grid of ProviderCards (list) and a
per-provider detail screen (shown when the user clicks CONFIGURE on a
card). The detail screen carries the API-key input for providers that
need one, plus a link out to the vendor's key-management page. All
credentials are held in a dict on the SettingsDialog so every tab's
detail view reads/writes through the same bag — keyless persistence
lives in the ApplicationController after Save.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from jarvis.ui import design
from jarvis.ui.components.provider_card import ProviderCard, ProviderOption
from jarvis.ui.components.provider_detail import ProviderDetailPanel


_ELEVENLABS_DEFAULT_VOICE_ID = "onwK4e9ZLuTAKqWW03F9"


# ── Provider catalogues ───────────────────────────────────────────────
# Defined as data (not inline constructor calls) so the catalogue reads
# top-to-bottom like a product spec.  Brand names use their canonical
# capitalisation — "OpenAI", not "openai" — per the user's request.


def _llm_options(
    has_groq_key: bool,
    has_openai_key: bool = False,
    has_anthropic_key: bool = False,
    has_gemini_key: bool = False,
) -> list[ProviderOption]:
    return [
        ProviderOption(
            key="groq",
            name="Groq",
            description=(
                "Cloud inference on Groq's LPU hardware. Sub-300ms first "
                "token on Llama 3.3 70B — fastest option for conversation."
            ),
            long_description=(
                "Groq runs large open-source models (Llama 3.3 70B, Qwen "
                "2.5 32B) on custom LPU silicon tuned for low-latency "
                "inference. The practical effect: Jarvis starts "
                "speaking ~250ms after you stop talking, vs 1-2s on a "
                "CPU-hosted local model. The free tier gives 1,000 "
                "requests/day on the 70B model — more than enough for "
                "daily personal use."
            ),
            strength="Best for real-time speed",
            example="Jarvis, what's the capital of Austria?",
            website="https://console.groq.com/keys",
            status="active" if has_groq_key else "ready",
            status_text="ACTIVE" if has_groq_key else "READY",
            credential_key="groq_api_key",
            credential_label="GROQ API KEY",
            credential_placeholder="gsk_...",
        ),
        ProviderOption(
            key="openai",
            name="OpenAI",
            description=(
                "GPT-4o-class reasoning. Most robust at interpreting odd "
                "phrasing and chaining multi-step commands."
            ),
            long_description=(
                "OpenAI's GPT models are the strongest option for "
                "complex multi-step reasoning and messy natural "
                "language. Integration coming soon — the Settings UI "
                "captures the key now so it's ready when the backend "
                "lands."
            ),
            strength="Best for complex commands",
            example="Jarvis, summarise my last three emails and draft a reply.",
            website="https://platform.openai.com/api-keys",
            status="active" if has_openai_key else "ready",
            status_text="ACTIVE" if has_openai_key else "REQUIRES KEY",
            credential_key="openai_api_key",
            credential_label="OPENAI API KEY",
            credential_placeholder="sk-...",
        ),
        ProviderOption(
            key="anthropic",
            name="Anthropic",
            description=(
                "Claude — careful, conversational, long-context. Preferred "
                "when you want considered answers over terse ones."
            ),
            long_description=(
                "Anthropic's Claude family excels at nuanced, "
                "considered responses and long-document reasoning. "
                "Integration planned for the next release."
            ),
            strength="Best for thoughtful chat",
            example="Jarvis, explain the tradeoffs of Rust vs Go.",
            website="https://console.anthropic.com/settings/keys",
            status="active" if has_anthropic_key else "ready",
            status_text="ACTIVE" if has_anthropic_key else "REQUIRES KEY",
            credential_key="anthropic_api_key",
            credential_label="ANTHROPIC API KEY",
            credential_placeholder="sk-ant-...",
        ),
        ProviderOption(
            key="gemini",
            name="Gemini",
            description=(
                "Google's multimodal model family. Strong at broad "
                "knowledge + integration with Google services."
            ),
            long_description=(
                "Google's Gemini models (1.5 Pro, Flash) offer native "
                "multimodal input and a generous free tier via AI "
                "Studio. Useful for anything touching Google services "
                "(Calendar, Drive, Search)."
            ),
            strength="Best for breadth + multimodal",
            example="Jarvis, what's on my calendar tomorrow?",
            website="https://aistudio.google.com/app/apikey",
            status="active" if has_gemini_key else "ready",
            status_text="ACTIVE" if has_gemini_key else "REQUIRES KEY",
            credential_key="gemini_api_key",
            credential_label="GOOGLE AI STUDIO KEY",
            credential_placeholder="AIza...",
        ),
        ProviderOption(
            key="lm_studio",
            name="Local AI",
            description=(
                "Runs a local model via LM Studio on your machine. No "
                "cloud calls, no limits, full privacy."
            ),
            long_description=(
                "LM Studio hosts any open-source model locally "
                "(Llama, Qwen, Mistral, Phi). Zero network latency, "
                "zero rate limits, zero data leaving the machine — "
                "at the cost of whatever GPU/CPU time your hardware "
                "can spare. Ideal for privacy-sensitive prompts or "
                "fully offline operation."
            ),
            strength="Best for privacy / offline",
            example="Jarvis, draft a note about my ideas for the pitch.",
            website="https://lmstudio.ai/",
            status="ready",
            status_text="READY",
            credential_key=None,
        ),
    ]


def _tts_options() -> list[ProviderOption]:
    return [
        ProviderOption(
            key="elevenlabs",
            name="ElevenLabs",
            description=(
                "Human-grade neural TTS with 1000+ voices, multilingual. "
                "Setting this is the single biggest voice quality upgrade."
            ),
            long_description=(
                "ElevenLabs runs the best consumer-facing neural TTS "
                "available — voices are indistinguishable from human "
                "recordings, and the multilingual v2 model carries the "
                "same voice across Portuguese, English, Spanish and "
                "27 other languages. Free tier includes ~10,000 "
                "characters/month (several hundred short responses). "
                "The default Daniel voice (British, deep) is the "
                "closest match to cinematic Jarvis in the stock library."
            ),
            strength="Best natural-sounding voice",
            example="Daniel · British, deep — the cinematic Jarvis",
            website="https://elevenlabs.io/app/settings/api-keys",
            status="ready",
            status_text="REQUIRES KEY",
            credential_key="elevenlabs_api_key",
            credential_label="ELEVENLABS API KEY",
            credential_placeholder="sk_...",
        ),
        ProviderOption(
            key="groq",
            name="Groq",
            description=(
                "Groq's hosted PlayAI TTS — fast, English-only. Free tier "
                "currently limited by provider-side model availability."
            ),
            long_description=(
                "Groq briefly offered PlayAI-powered TTS as an add-on "
                "to their LLM stack. The model was decommissioned "
                "upstream, so this option is parked until Groq ships "
                "a replacement. Your Groq API key in Credentials still "
                "drives LLM + STT regardless."
            ),
            strength="Fast, free with Groq key",
            example="Atlas · American, deep baritone",
            website="https://console.groq.com/",
            status="coming_soon",
            status_text="MODEL DEPRECATED",
            credential_key=None,
        ),
        ProviderOption(
            key="streamlabs",
            name="Streamlabs",
            description=(
                "Streamlabs Cloudbot voices — varied character voices, "
                "popular with creators. Integration planned."
            ),
            long_description=(
                "Streamlabs' Cloudbot exposes dozens of TTS voices — "
                "Brian, Amy, Justin, etc — widely used in livestream "
                "tooling. Integration is on the roadmap; this entry "
                "tracks it so you know it's coming."
            ),
            strength="Best for creator voices",
            example="Brian · male, mid-depth",
            website="https://streamlabs.com/",
            status="coming_soon",
            status_text="COMING SOON",
            credential_key=None,
        ),
        ProviderOption(
            key="piper",
            name="Local Voice",
            description=(
                "Local Piper synthesizer bundled with Jarvis. Offline, "
                "instant, solid quality in PT-BR."
            ),
            long_description=(
                "Piper is a lightweight on-device TTS bundled with "
                "Jarvis. Latency is near-zero (no network round-trip) "
                "and quality is good for Portuguese. English voices "
                "are available separately but the stock install only "
                "ships pt_BR-faber — switch JARVIS_LANGUAGE to pt-BR "
                "if you want to use Piper exclusively."
            ),
            strength="Best for offline / no keys",
            example="Faber · PT-BR masculine",
            website="https://github.com/rhasspy/piper",
            status="ready",
            status_text="READY",
            credential_key=None,
        ),
    ]


def _music_options() -> list[ProviderOption]:
    return [
        ProviderOption(
            key="spotify",
            name="Spotify",
            description=(
                "Jarvis drives Spotify Desktop via the official Web API "
                "(PKCE, no secrets). Search + play any track from your "
                "library or the catalogue."
            ),
            long_description=(
                "Spotify integration uses OAuth PKCE — no client "
                "secret, no credentials in the repo. Register a free "
                "app in the developer dashboard, paste the Client ID "
                "below, and Jarvis can search + play any track on any "
                "of your active Spotify devices. Falls back to "
                "keyboard shortcuts if the API isn't configured, but "
                "that mode is much less reliable."
            ),
            strength="Full catalogue, precise control",
            example="Jarvis, play Back in Black on Spotify.",
            website="https://developer.spotify.com/dashboard",
            status="ready",
            status_text="READY",
            credential_key="spotify_client_id",
            credential_label="SPOTIFY CLIENT ID",
            credential_placeholder="57c1ae19...",
        ),
        ProviderOption(
            key="soundcloud",
            name="SoundCloud",
            description=(
                "SoundCloud search and playback. Great for remixes, DJ "
                "sets and independent uploads the other services miss."
            ),
            long_description=(
                "SoundCloud integration is on the roadmap. Useful for "
                "content that doesn't live on Spotify: live sets, "
                "podcast episodes, remix uploads, producer demos. "
                "This card exists so you know it's coming."
            ),
            strength="Best for mixes + indie uploads",
            example="Jarvis, find a 90-minute liquid DnB set on SoundCloud.",
            website="https://soundcloud.com/",
            status="coming_soon",
            status_text="COMING SOON",
            credential_key=None,
        ),
    ]


# ── Dialog ────────────────────────────────────────────────────────────


class SettingsDialog(QDialog):
    """Tabbed settings dialog. Exposes current choices + raw keys via
    properties — the ApplicationController reads them on Save."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        llm_provider: str = "groq",
        tts_provider: str = "piper",
        music_provider: str = "spotify",
        spotify_client_id: str = "",
        groq_api_key: str = "",
        elevenlabs_api_key: str = "",
        elevenlabs_voice_id: str = _ELEVENLABS_DEFAULT_VOICE_ID,
        openai_api_key: str = "",
        anthropic_api_key: str = "",
        gemini_api_key: str = "",
    ) -> None:
        super().__init__(parent)
        self._drag_origin: QPoint | None = None

        self.setWindowTitle("Jarvis — Settings")
        self.setModal(True)
        self.setFixedSize(1020, 780)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Shared credential bag — the detail view of every tab reads
        # and writes through this dict so each provider's API key is
        # available regardless of which tab exposed it. Keys here
        # match the `credential_key` field on ProviderOption.
        self._credentials: dict[str, str] = {
            "spotify_client_id": spotify_client_id.strip(),
            "groq_api_key": groq_api_key.strip(),
            "elevenlabs_api_key": elevenlabs_api_key.strip(),
            "elevenlabs_voice_id": (elevenlabs_voice_id or _ELEVENLABS_DEFAULT_VOICE_ID).strip(),
            "openai_api_key": openai_api_key.strip(),
            "anthropic_api_key": anthropic_api_key.strip(),
            "gemini_api_key": gemini_api_key.strip(),
        }

        # Pre-select picked provider from settings when building each tab.
        self._intelligence_tab = _CardPickerTab(
            options=_llm_options(
                has_groq_key=bool(groq_api_key),
                has_openai_key=bool(openai_api_key),
                has_anthropic_key=bool(anthropic_api_key),
                has_gemini_key=bool(gemini_api_key),
            ),
            initial_key=llm_provider,
            credential_reader=self._credentials.get,
            credential_writer=self._credentials.__setitem__,
            empty_hint="No AI provider configured.",
        )
        self._voice_tab = _CardPickerTab(
            options=_tts_options(),
            initial_key=tts_provider,
            credential_reader=self._credentials.get,
            credential_writer=self._credentials.__setitem__,
            empty_hint="No TTS engine configured.",
        )
        self._music_tab = _CardPickerTab(
            options=_music_options(),
            initial_key=music_provider,
            credential_reader=self._credentials.get,
            credential_writer=self._credentials.__setitem__,
            empty_hint="No music provider configured.",
        )

        self._build()
        self.setStyleSheet(design.global_stylesheet())

    # ── public getters ─────────────────────────────────────────────────

    @property
    def llm_provider(self) -> str:
        return self._intelligence_tab.selected_key

    @property
    def tts_provider(self) -> str:
        return self._voice_tab.selected_key

    @property
    def music_provider(self) -> str:
        return self._music_tab.selected_key

    @property
    def spotify_client_id(self) -> str:
        return self._credentials.get("spotify_client_id", "").strip()

    @property
    def groq_api_key(self) -> str:
        return self._credentials.get("groq_api_key", "").strip()

    @property
    def elevenlabs_api_key(self) -> str:
        return self._credentials.get("elevenlabs_api_key", "").strip()

    @property
    def elevenlabs_voice_id(self) -> str:
        return self._credentials.get("elevenlabs_voice_id", "").strip() or _ELEVENLABS_DEFAULT_VOICE_ID

    @property
    def openai_api_key(self) -> str:
        return self._credentials.get("openai_api_key", "").strip()

    @property
    def anthropic_api_key(self) -> str:
        return self._credentials.get("anthropic_api_key", "").strip()

    @property
    def gemini_api_key(self) -> str:
        return self._credentials.get("gemini_api_key", "").strip()

    # ── build ──────────────────────────────────────────────────────────

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            design.SPACE_5, design.SPACE_5, design.SPACE_5, design.SPACE_5
        )

        frame = QFrame()
        frame.setObjectName("rootFrame")
        root = QVBoxLayout(frame)
        root.setContentsMargins(
            design.SPACE_8, design.SPACE_6, design.SPACE_8, design.SPACE_6
        )
        root.setSpacing(design.SPACE_5)

        root.addLayout(self._build_header())

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.addTab(self._intelligence_tab, "  INTELLIGENCE  ")
        tabs.addTab(self._voice_tab, "  VOICE  ")
        tabs.addTab(self._music_tab, "  MUSIC  ")
        root.addWidget(tabs, 1)

        root.addLayout(self._build_footer())

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(60)
        shadow.setOffset(0, 0)
        shadow.setColor(QColor(0, 240, 255, 80))
        frame.setGraphicsEffect(shadow)

        outer.addWidget(frame)

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(design.SPACE_4)

        title = QLabel("SETTINGS")
        title.setProperty("role", "title")
        subtitle = QLabel(" · JARVIS CONTROL PANEL")
        subtitle.setProperty("role", "subtitle")
        row.addWidget(title)
        row.addWidget(subtitle)
        row.addStretch(1)

        close_button = QPushButton("×")
        close_button.setProperty("variant", "icon")
        close_button.setFixedSize(32, 32)
        close_button.clicked.connect(self.reject)
        row.addWidget(close_button)
        return row

    def _build_footer(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(design.SPACE_2)
        hint = QLabel("Changes apply after the next assistant turn.")
        hint.setProperty("role", "muted")
        row.addWidget(hint)
        row.addStretch(1)

        cancel = QPushButton("CANCEL")
        cancel.setProperty("variant", "ghost")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)

        save = QPushButton("SAVE CHANGES")
        save.setProperty("variant", "primary")
        save.setDefault(True)
        save.clicked.connect(self.accept)
        row.addWidget(save)
        return row

    # ── drag to move (frameless window) ───────────────────────────────

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_origin)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_origin = None
        super().mouseReleaseEvent(event)


# ── Card picker tab ──────────────────────────────────────────────────


class _CardPickerTab(QWidget):
    """Tab with two pages stacked in a QStackedWidget:

    - index 0: list view — grid of ProviderCards, user clicks
      CONFIGURE on one.
    - index 1: detail view for whichever card was clicked. Shows the
      full description and the API credential input (if any).

    Clicking a card's Select button sets that provider as the active
    choice AND navigates to the detail view so the user can paste the
    key immediately. Back from detail returns to the list with the
    new selection reflected in the card's "CONFIGURED" state.
    """

    def __init__(
        self,
        options: list[ProviderOption],
        initial_key: str,
        credential_reader,
        credential_writer,
        empty_hint: str,
    ) -> None:
        super().__init__()
        self._options = options
        self._option_by_key = {o.key: o for o in options}
        self._selected_key = initial_key if initial_key in self._option_by_key else (
            options[0].key if options else ""
        )
        self._cards: dict[str, ProviderCard] = {}
        self._credential_reader = credential_reader
        self._credential_writer = credential_writer

        root = QVBoxLayout(self)
        root.setContentsMargins(
            design.SPACE_3, design.SPACE_4, design.SPACE_3, design.SPACE_3
        )
        root.setSpacing(design.SPACE_3)

        if not options:
            empty = QLabel(empty_hint)
            empty.setProperty("role", "muted")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            root.addWidget(empty, 1)
            return

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_list_view())
        self._detail_host = QWidget()
        self._detail_layout = QVBoxLayout(self._detail_host)
        self._detail_layout.setContentsMargins(0, 0, 0, 0)
        self._stack.addWidget(self._detail_host)
        root.addWidget(self._stack, 1)

        self._apply_initial_selection()

    @property
    def selected_key(self) -> str:
        return self._selected_key

    # ── list view ────────────────────────────────────────────────────

    def _build_list_view(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(
            design.SPACE_2, design.SPACE_2, design.SPACE_2, design.SPACE_2
        )
        grid.setHorizontalSpacing(design.SPACE_4)
        grid.setVerticalSpacing(design.SPACE_4)

        for index, opt in enumerate(self._options):
            card = ProviderCard(opt)
            card.select_requested.connect(self._on_select_clicked)
            card.configure_requested.connect(self._on_configure_clicked)
            self._cards[opt.key] = card
            grid.addWidget(card, index // 2, index % 2)
        grid.setRowStretch(grid.rowCount(), 1)

        scroll.setWidget(grid_host)
        return scroll

    # ── selection + navigation ───────────────────────────────────────

    def _apply_initial_selection(self) -> None:
        for key, card in self._cards.items():
            card.set_selected(key == self._selected_key)

    def _on_select_clicked(self, key: str) -> None:
        """Pure selection — mark this provider as the active one
        without navigating away. Lets the user swap between providers
        with a single click each, which is what the picker UX should
        feel like."""
        if key not in self._option_by_key or key == self._selected_key:
            return
        self._selected_key = key
        for card_key, card in self._cards.items():
            card.set_selected(card_key == key)

    def _on_configure_clicked(self, key: str) -> None:
        option = self._option_by_key.get(key)
        if option is None:
            return
        # Opening CONFIGURE also implies "I want to use this one" —
        # matches the user's mental model of entering a credential
        # ("setting this up"). Keeps selection + config coherent.
        if key != self._selected_key:
            self._selected_key = key
            for card_key, card in self._cards.items():
                card.set_selected(card_key == key)

        # Swap the detail view for this provider. Creating a fresh
        # ProviderDetailPanel each time keeps the inputs in sync with
        # whatever the shared credential bag holds right now.
        self._clear_detail_host()
        panel = ProviderDetailPanel(
            option=option,
            get_credential=lambda k: self._credential_reader(k, ""),
            set_credential=self._credential_writer,
        )
        panel.back_requested.connect(self._show_list_view)
        self._detail_layout.addWidget(panel)
        self._stack.setCurrentIndex(1)

    def _clear_detail_host(self) -> None:
        while self._detail_layout.count():
            item = self._detail_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _show_list_view(self) -> None:
        self._stack.setCurrentIndex(0)
        self._clear_detail_host()


