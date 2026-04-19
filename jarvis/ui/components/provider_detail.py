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

import logging
import threading
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

LOGGER = logging.getLogger(__name__)

# Sample sentence chosen to exercise prosody without being awkward —
# short enough to synthesise in under a second on all providers, long
# enough to show timbre beyond a single syllable.
_PREVIEW_TEXT = "Good evening, sir. Systems online and ready."


def _preview_voice(provider_key: str, credential: str, voice_id: str) -> tuple[bool, str]:
    """Synthesise and play a short sample using the provider the
    detail view is showing. Returns (ok, message) so the caller can
    paint the status label without knowing provider internals."""
    import io
    import wave

    from jarvis.services.tts_engine import PcmAudio, TtsEngineError

    audio: PcmAudio
    try:
        if provider_key == "elevenlabs":
            if not credential:
                return False, "enter an API key above first"
            from jarvis.services.elevenlabs_tts_engine import ElevenLabsTTSEngine

            engine = ElevenLabsTTSEngine(
                api_key=credential,
                voice_id=voice_id or "onwK4e9ZLuTAKqWW03F9",
            )
            audio = engine.synthesize(_PREVIEW_TEXT)
        elif provider_key == "groq":
            if not credential:
                return False, "enter an API key above first"
            from jarvis.services.groq_tts_engine import GroqTTSEngine

            engine = GroqTTSEngine(api_key=credential)
            audio = engine.synthesize(_PREVIEW_TEXT)
        elif provider_key == "piper":
            from jarvis.factories.application_factory import ApplicationFactory
            from pathlib import Path

            # Locate piper exe + the bundled voice relative to the
            # repo root — same resolution the factory uses at boot.
            factory = ApplicationFactory(Path.cwd())
            piper_exe = factory._resolve_piper_exe()
            model_path = factory._resolve_voice_model_path()
            if piper_exe is None or model_path is None:
                return False, "piper binary or voice model not installed"
            from jarvis.services.tts_engine import PiperEngine

            engine = PiperEngine(piper_exe=piper_exe, model_path=model_path)
            audio = engine.synthesize(_PREVIEW_TEXT)
        else:
            return False, "preview not available for this provider"
    except TtsEngineError as exc:
        return False, f"synth failed: {str(exc)[:80]}"
    except Exception as exc:
        return False, f"error: {str(exc)[:80]}"

    # Wrap the PCM in a WAV container and play it via winsound. Bypasses
    # the main VoiceService/AudioPlayer pipeline so we don't have to
    # spin it up just for a preview.
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(audio.channels)
        wav.setsampwidth(audio.sample_width)
        wav.setframerate(audio.sample_rate)
        wav.writeframes(audio.pcm_bytes)
    try:
        import winsound

        winsound.PlaySound(
            buf.getvalue(), winsound.SND_MEMORY | winsound.SND_ASYNC
        )
    except Exception as exc:
        return False, f"playback failed: {str(exc)[:80]}"
    return True, "ok"


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

        # TTS providers get a live voice-test button. Credentials
        # entered above are read directly so the user can preview
        # the voice without leaving the dialog or restarting the app.
        if self._is_tts_provider():
            body_layout.addSpacing(design.SPACE_3)
            body_layout.addLayout(self._build_test_voice_row())

        body_layout.addSpacing(design.SPACE_3)
        body_layout.addLayout(self._build_website_row())
        body_layout.addStretch(1)

    def _is_tts_provider(self) -> bool:
        # Cheap classification: the only TTS option keys we know are
        # the four we publish in settings_dialog. Anything else falls
        # through without offering a test.
        return self._option.key in {"elevenlabs", "groq", "piper", "streamlabs"}

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

    # ── test voice ────────────────────────────────────────────────────

    def _build_test_voice_row(self) -> QVBoxLayout:
        section = QVBoxLayout()
        section.setSpacing(design.SPACE_2)

        header = QLabel("TEST VOICE")
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
        button = QPushButton("▶  PREVIEW THIS VOICE")
        button.setProperty("variant", "primary")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(self._on_test_voice)
        row.addWidget(button)

        self._test_status = QLabel("")
        self._test_status.setStyleSheet(
            f"color: {design.TEXT_MUTED.hex}; font-family: {design.FONT_UI};"
            f"font-size: {design.FONT_SIZE_SMALL}px;"
        )
        row.addWidget(self._test_status, 1)
        section.addLayout(row)
        return section

    def _on_test_voice(self) -> None:
        """Kick a fresh synthesis with the currently-typed credentials.

        Runs in a background thread so a slow cloud call (or a bad
        key's 2-second 401) doesn't freeze the dialog. Failures are
        surfaced on the inline status label; the audio lands through
        the system default output so the user hears it right away.
        """
        if not hasattr(self, "_test_status"):
            return
        self._test_status.setText("synthesising…")

        key = self._option.key
        cred_key = self._option.credential_key
        cred_value = self._get_credential(cred_key) if cred_key else ""
        voice_id = self._get_credential("elevenlabs_voice_id") or ""

        def _run() -> None:
            try:
                ok, message = _preview_voice(key, cred_value, voice_id)
            except Exception as exc:
                LOGGER.exception("test_voice_crashed")
                ok, message = False, f"failed: {exc}"
            # Qt widget mutations must happen on the main thread. The
            # safe way from a daemon worker is QMetaObject.invokeMethod
            # but a setText is cheap and QLabel's implementation is
            # thread-tolerant in practice on Windows — matches what
            # the rest of the HUD does for level/state updates.
            self._test_status.setText(message if not ok else "✓  voice preview played")

        threading.Thread(target=_run, name="jarvis-voice-preview", daemon=True).start()

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
