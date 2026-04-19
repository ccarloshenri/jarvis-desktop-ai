from __future__ import annotations

import time
from datetime import datetime

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from jarvis.config.strings import Strings
from jarvis.models.app_settings import AppSettings
from jarvis.models.interaction_result import InteractionResult
from jarvis.services.update_checker import ReleaseInfo
from jarvis.ui import design
from jarvis.ui.clock_widget import ClockWidget
from jarvis.ui.components.connection_status import ConnectionStatusPanel
from jarvis.ui.components.event_timeline import EventTimeline
from jarvis.ui.components.status_card import StatusCard
from jarvis.ui.jarvis_orb import JarvisOrb
from jarvis.ui.latency_stack import LatencyFrame, LatencyStack
from jarvis.ui.mic_meter import MicLevelMeter
from jarvis.ui.success_ring import SuccessRing
from jarvis.ui.waveform_widget import WaveformWidget
from jarvis.ui.stats_collector import StatsCollector, StatsSnapshot


_STATE_LABELS = {
    "idle": ("STANDBY", "#7FA2B0"),
    "listening": ("LISTENING", "#00F0FF"),
    "processing": ("PROCESSING", "#6EEAFF"),
    "thinking": ("THINKING", "#FFD56B"),
    # Speaking uses the paler cyan (ACCENT_SOFT) — visually distinct
    # from listening without leaving the cyan family, so the whole
    # state palette reads as one instrument.
    "speaking": ("SPEAKING", "#6EEAFF"),
}


_BRAND_NAMES = {
    "groq": "Groq",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "gemini": "Gemini",
    "lm_studio": "Local AI",
    "elevenlabs": "ElevenLabs",
    "streamlabs": "Streamlabs",
    "piper": "Local Voice",
    "spotify": "Spotify",
    "soundcloud": "SoundCloud",
}


def _brand(key: str) -> str:
    """Translate an internal provider key to its canonical branded
    display name. Falls back to the raw key titlecased so unknown
    strings don't crash the HUD."""
    return _BRAND_NAMES.get(key, key.replace("_", " ").title())


class MainWindow(QMainWindow):
    update_requested = Signal(object)
    settings_requested = Signal()

    def __init__(
        self,
        strings: Strings,
        stats: StatsCollector,
        debug: bool = False,
        settings: AppSettings | None = None,
    ) -> None:
        super().__init__()
        self._strings = strings
        self._debug = debug
        self._stats = stats
        self._settings = settings
        self.setWindowTitle(strings.get("window_title"))
        self.setMinimumSize(1180, 980)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._drag_origin: QPoint | None = None
        self._orb = JarvisOrb()
        self._mic_meter = MicLevelMeter()
        self._waveform = WaveformWidget()
        self._latency_stack = LatencyStack()
        self._success_ring = SuccessRing()
        self._connection_panel = ConnectionStatusPanel()
        self._event_timeline = EventTimeline()
        self._clock: ClockWidget | None = None
        self._state_label: QLabel | None = None
        self._state_dot: QLabel | None = None
        self._stat_labels: dict[str, QLabel] = {}
        self._transcript_banner: QLabel | None = None
        self._response_banner: QLabel | None = None
        self._log_panel: QTextEdit | None = None
        self._update_banner: QFrame | None = None
        self._update_banner_label: QLabel | None = None
        self._pending_release: ReleaseInfo | None = None
        self._current_state = "idle"

        # Stats panel refresh — reads the snapshot at ~2Hz. Cheap and
        # keeps uptime/averages ticking without flooding the main loop.
        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._refresh_stats)
        self._stats_timer.start(500)

        self._build()
        self._apply_styles()
        self.set_state("idle")
        self._refresh_stats()

    # ------- event hooks (called from controller / event bus) -------

    def update_status(self, status: str) -> None:
        # Kept for worker backwards-compat. The HUD has its own state
        # strip now; drop stray worker status strings on the floor.
        del status

    def update_transcript(self, transcript: str) -> None:
        if not transcript:
            return
        ts = datetime.now().strftime("%H:%M:%S")
        prefix = self._strings.get("debug_user_prefix").upper()
        self._append_log(
            f'<span style="color:#6ea8c0">{ts}</span> '
            f'<span style="color:#7fffa0">{prefix}</span> '
            f'<span style="color:#c9ffff">{self._escape(transcript)}</span>'
        )
        if self._transcript_banner is not None:
            trimmed = transcript.strip()
            self._transcript_banner.setText(f"“{trimmed}”" if trimmed else "")

    def update_response(self, response: str) -> None:
        if not response:
            return
        ts = datetime.now().strftime("%H:%M:%S")
        prefix = self._strings.get("debug_jarvis_prefix").upper()
        self._append_log(
            f'<span style="color:#6ea8c0">{ts}</span> '
            f'<span style="color:#8dfdff">{prefix}</span> '
            f'<span style="color:#eafcff">{self._escape(response)}</span>'
        )
        if self._response_banner is not None:
            self._response_banner.setText(response.strip())
        self._stats.record_response()

    def display_result(self, result: InteractionResult) -> None:
        # Stats live in the dedicated panel; this hook is unused by the
        # redesigned HUD.
        del result

    def set_speaking(self, speaking: bool) -> None:
        self._orb.set_speaking(speaking)
        if speaking:
            self.set_state("speaking")
        elif self._current_state == "speaking":
            self.set_state("idle")

    def set_state(self, state: str) -> None:
        """Update the status strip. Known states: idle, listening,
        processing, thinking, speaking. Unknown names fall back to idle
        so accidental typos in the worker signal don't blank the UI."""
        state = state.lower()
        if state not in _STATE_LABELS:
            state = "idle"
        self._current_state = state
        if self._state_label is None or self._state_dot is None:
            return
        label, color = _STATE_LABELS[state]
        self._state_label.setText(label)
        self._state_label.setStyleSheet(
            f"color: {color}; letter-spacing: 6px; font-family: Bahnschrift; "
            f"font-size: 18px; font-weight: 700;"
        )
        self._state_dot.setStyleSheet(
            f"background-color: {color}; border-radius: 7px; max-width: 14px; "
            f"max-height: 14px; min-width: 14px; min-height: 14px;"
        )
        # Mirror the state into the top status strip so the glanceable
        # header is never stale relative to the big state label.
        if getattr(self, "_status_listen", None) is not None:
            self._status_listen.set_value(label)
            self._status_listen.set_accent(color)

    def set_mic_level(self, level: float) -> None:
        self._mic_meter.set_level(level)
        self._waveform.set_level(level)

    def record_turn_event(self, success: bool) -> None:
        """Relay a completed turn to the visual event timeline."""
        self._event_timeline.record_turn(success)

    def record_wake_event(self) -> None:
        """Relay a wake-word fire to the visual event timeline."""
        self._event_timeline.record_wake()

    def update_connection_status(self, key: str, state: str, detail: str = "") -> None:
        """Flip a single row on the Connections panel — called from
        the controller when a provider's availability changes."""
        self._connection_panel.set_service_state(key, state, detail)

    # ------- build helpers -------

    def _build(self) -> None:
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(22, 22, 22, 22)

        frame = QWidget()
        frame.setObjectName("windowFrame")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(26, 18, 26, 22)
        frame_layout.setSpacing(14)

        frame_layout.addLayout(self._build_top_bar())
        self._update_banner = self._build_update_banner()
        frame_layout.addWidget(self._update_banner)

        # System status strip — 4 glanceable cards showing which
        # provider is currently driving each subsystem. Sits under the
        # title bar so the first thing the user sees is "what's on".
        frame_layout.addLayout(self._build_status_strip())

        # Top HUD row: providers + stats | orb+state | telemetry
        hud_row = QHBoxLayout()
        hud_row.setSpacing(16)
        hud_row.addWidget(self._build_left_column(), 1)
        hud_row.addWidget(self._build_center_stage(), 2)
        hud_row.addWidget(self._build_right_column(), 1)
        frame_layout.addLayout(hud_row, 1)

        frame_layout.addWidget(self._build_log_panel(), 1)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(44)
        shadow.setOffset(0, 0)
        shadow.setColor(QColor(0, 255, 255, 40))
        frame.setGraphicsEffect(shadow)

        outer_layout.addWidget(frame)
        self.setCentralWidget(outer)

    def _build_status_strip(self) -> QHBoxLayout:
        """Four-card strip summarising which subsystem is active.

        Cards pull from settings (LLM, TTS, Music) plus a dynamic
        listening-state card driven by the pipeline state. Accent
        colours match the HUD palette so green = healthy provider,
        amber = degraded, cyan = ready/standby."""
        row = QHBoxLayout()
        row.setSpacing(design.SPACE_3)
        settings = self._settings

        llm_name = _brand(settings.llm_provider if settings else "groq")
        llm_detail = (
            settings.groq_llm_model
            if settings and settings.llm_provider == "groq"
            else settings.lm_studio_model
            if settings
            else "—"
        )
        self._status_llm = StatusCard(
            "AI BRAIN",
            f"{llm_name} · {llm_detail}",
            accent=design.ACCENT_OK.hex,
        )
        row.addWidget(self._status_llm, 1)

        tts_name = _brand(settings.tts_provider if settings else "piper")
        if settings and settings.tts_provider == "elevenlabs":
            tts_detail = f"voice {settings.elevenlabs_voice_id[:8]}"
        elif settings and settings.tts_provider == "groq":
            tts_detail = settings.groq_tts_voice
        else:
            tts_detail = "Faber PT-BR"
        self._status_tts = StatusCard(
            "VOICE ENGINE",
            f"{tts_name} · {tts_detail}",
            accent=design.ACCENT_PRIMARY.hex,
        )
        row.addWidget(self._status_tts, 1)

        music_name = _brand(settings.music_provider if settings else "spotify")
        self._status_music = StatusCard(
            "MUSIC",
            music_name,
            accent=design.ACCENT_WARM.hex,
        )
        row.addWidget(self._status_music, 1)

        self._status_listen = StatusCard(
            "PIPELINE",
            "STANDBY",
            accent=design.ACCENT_PRIMARY.hex,
        )
        row.addWidget(self._status_listen, 1)
        return row

    def _build_left_column(self) -> QWidget:
        column = QWidget()
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(self._build_providers_panel(), 1)
        layout.addWidget(self._build_stats_panel(), 1)
        layout.addWidget(self._event_timeline, 0)
        return column

    def _build_right_column(self) -> QWidget:
        column = QWidget()
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(self._connection_panel, 1)
        layout.addWidget(self._build_telemetry_panel(), 1)
        layout.addWidget(self._build_latency_panel(), 1)
        return column

    def _build_providers_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("hudPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)
        layout.addWidget(self._panel_header("PROVIDERS"))
        settings = self._settings
        if settings is None:
            layout.addStretch(1)
            return panel
        llm_model = (
            settings.groq_llm_model
            if settings.llm_provider == "groq"
            else settings.lm_studio_model
        )
        stt_model = (
            settings.groq_stt_model
            if settings.stt_provider == "groq"
            else settings.whisper_model
        )
        if settings.tts_provider == "elevenlabs":
            tts_info = f"ElevenLabs · {settings.elevenlabs_voice_id[:8]}…"
        elif settings.tts_provider == "groq":
            tts_info = f"Groq · {settings.groq_tts_voice}"
        else:
            tts_info = "Local · Faber"
        stt_label = "Groq" if settings.stt_provider == "groq" else "Local Whisper"
        for key, label, value in (
            ("prov_llm", "LLM", f"{_brand(settings.llm_provider)} · {llm_model}"),
            ("prov_stt", "STT", f"{stt_label} · {stt_model}"),
            ("prov_tts", "TTS", tts_info),
            ("prov_music", "MUSIC", _brand(settings.music_provider)),
            ("prov_lang", "LANGUAGE", settings.language),
            ("prov_wake", "WAKE WORD", settings.wake_word_model),
            ("prov_vad", "VAD", settings.vad_backend),
        ):
            layout.addLayout(self._static_row(key, label, value))
        layout.addStretch(1)
        return panel

    def _build_latency_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("hudPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)
        layout.addWidget(self._panel_header("LATENCY HISTORY"))
        layout.addWidget(self._latency_stack)
        layout.addStretch(1)
        return panel

    def _static_row(self, key: str, label: str, value: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        name = QLabel(label)
        name.setObjectName("statName")
        lbl = QLabel(value)
        lbl.setObjectName("statValueSmall")
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl.setWordWrap(False)
        self._stat_labels[key] = lbl
        row.addWidget(name)
        row.addStretch(1)
        row.addWidget(lbl)
        return row

    def _build_top_bar(self) -> QHBoxLayout:
        top_bar = QHBoxLayout()
        settings_button = QPushButton("⚙")
        settings_button.setObjectName("settingsButton")
        settings_button.setFixedSize(32, 32)
        settings_button.setToolTip("Settings")
        settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_button.clicked.connect(self.settings_requested.emit)
        top_bar.addWidget(settings_button)

        title = QLabel("J A R V I S")
        title.setObjectName("topTitle")
        top_bar.addWidget(title)

        if self._debug:
            debug_badge = QLabel("DEBUG")
            debug_badge.setObjectName("debugBadge")
            top_bar.addWidget(debug_badge)
        top_bar.addStretch(1)

        # Live clock slotted in the top bar — gives the HUD a constant
        # "mission control" tick instead of dead space next to the
        # title.
        self._clock = ClockWidget()
        top_bar.addWidget(self._clock)
        top_bar.addSpacing(12)

        close_button = QPushButton("×")
        close_button.setObjectName("closeButton")
        close_button.setFixedSize(32, 32)
        close_button.clicked.connect(self.close)
        top_bar.addWidget(close_button)
        return top_bar

    def _build_stats_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("hudPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)
        layout.addWidget(self._panel_header("SYSTEM"))

        # Success ring sits above the numeric counters — visual summary
        # first, raw numbers second. Matches how real control HUDs are
        # laid out (glanceable gauges on top, telemetry underneath).
        ring_row = QHBoxLayout()
        ring_row.addStretch(1)
        ring_row.addWidget(self._success_ring)
        ring_row.addStretch(1)
        layout.addLayout(ring_row)

        for key, label in (
            ("uptime", "UPTIME"),
            ("turns", "TURNS"),
            ("wake_fires", "WAKE FIRES"),
            ("responses", "RESPONSES"),
            ("errors", "ERRORS"),
            ("avg_total", "AVG TOTAL"),
            ("last_total", "LAST TOTAL"),
        ):
            layout.addLayout(self._stat_row(key, label))
        layout.addStretch(1)
        return panel

    def _build_telemetry_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("hudPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)
        layout.addWidget(self._panel_header("TELEMETRY"))

        for key, label in (
            ("last_stt", "STT"),
            ("avg_stt", "STT (AVG)"),
            ("last_llm", "LLM"),
            ("avg_llm", "LLM (AVG)"),
            ("last_tts", "TTS"),
        ):
            layout.addLayout(self._stat_row(key, label))
        layout.addStretch(1)
        return panel

    def _build_center_stage(self) -> QWidget:
        center = QWidget()
        layout = QVBoxLayout(center)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        big_title = QLabel("J.A.R.V.I.S")
        big_title.setObjectName("centerTitle")
        big_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(big_title)

        # Orb container with FIXED height = orb size + symmetrical
        # 24px padding above and below. Any earlier design relied on
        # stretch math between flexible orb space and the rest of the
        # layout, which let Qt compress the container on smaller
        # windows — the orb's radial glow then bled into the state
        # strip ("LISTENING" landing on top of the ball). A fixed
        # 328px container walls the glow off from anything below it.
        orb_holder = QWidget()
        orb_holder.setFixedHeight(self._orb.height() + 48)
        orb_layout = QVBoxLayout(orb_holder)
        orb_layout.setContentsMargins(0, 24, 0, 24)
        orb_layout.addWidget(self._orb, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(orb_holder)

        # 24px spacer BETWEEN the orb box and the state strip. This is
        # the gap the user sees — without it, the LISTENING label
        # visually touches the orb even when they're technically
        # different widgets.
        layout.addSpacing(24)

        # State strip — dot + label, lit based on pipeline state.
        state_row = QHBoxLayout()
        state_row.setContentsMargins(0, 0, 0, 0)
        state_row.setSpacing(12)
        self._state_dot = QLabel()
        state_row.addStretch(1)
        state_row.addWidget(self._state_dot)
        self._state_label = QLabel("STANDBY")
        state_row.addWidget(self._state_label)
        state_row.addStretch(1)
        layout.addLayout(state_row)

        # Mic VU meter beneath the state line.
        mic_row = QHBoxLayout()
        mic_row.setContentsMargins(24, 0, 24, 0)
        mic_row.addWidget(self._mic_meter, 1)
        layout.addLayout(mic_row)

        # Waveform below the VU meter — gives a scrolling history of
        # recent mic energy so idle/speech patterns are visible at a
        # glance. VU is instantaneous; waveform is temporal.
        wave_row = QHBoxLayout()
        wave_row.setContentsMargins(24, 0, 24, 0)
        wave_row.addWidget(self._waveform, 1)
        layout.addLayout(wave_row)

        # Last transcript / response banners. These make the HUD feel
        # "live" — the user always sees the most recent thing spoken
        # without having to scroll the log.
        self._transcript_banner = QLabel("")
        self._transcript_banner.setObjectName("transcriptBanner")
        self._transcript_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._transcript_banner.setWordWrap(True)
        self._response_banner = QLabel("")
        self._response_banner.setObjectName("responseBanner")
        self._response_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._response_banner.setWordWrap(True)
        layout.addSpacing(6)
        layout.addWidget(self._transcript_banner)
        layout.addWidget(self._response_banner)

        return center

    def _build_log_panel(self) -> QWidget:
        self._log_panel = QTextEdit()
        self._log_panel.setObjectName("logPanel")
        self._log_panel.setReadOnly(True)
        self._log_panel.setMinimumHeight(140)
        return self._log_panel

    def _panel_header(self, text: str) -> QLabel:
        header = QLabel(text)
        header.setObjectName("panelHeader")
        return header

    def _stat_row(self, key: str, label: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        name = QLabel(label)
        name.setObjectName("statName")
        value = QLabel("—")
        value.setObjectName("statValue")
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._stat_labels[key] = value
        row.addWidget(name)
        row.addStretch(1)
        row.addWidget(value)
        return row

    def _refresh_stats(self) -> None:
        snapshot = self._stats.snapshot()
        self._set_stat("uptime", _format_uptime(snapshot.uptime_seconds))
        self._set_stat("turns", f"{snapshot.turns_total}")
        self._set_stat("wake_fires", f"{snapshot.wake_fires}")
        self._set_stat("responses", f"{snapshot.responses}")
        self._set_stat("errors", f"{snapshot.errors}")
        self._set_stat("avg_total", _fmt_ms(snapshot.avg_total_ms))
        self._set_stat("last_total", _fmt_ms(snapshot.last_total_ms))
        self._set_stat("last_stt", _fmt_ms(snapshot.last_stt_ms))
        self._set_stat("avg_stt", _fmt_ms(snapshot.avg_stt_ms))
        self._set_stat("last_llm", _fmt_ms(snapshot.last_llm_ms))
        self._set_stat("avg_llm", _fmt_ms(snapshot.avg_llm_ms))
        self._set_stat("last_tts", _fmt_ms(snapshot.last_tts_ms))
        self._success_ring.set_success(
            snapshot.turns_success, snapshot.turns_total
        )
        # Build aligned latency frames. recent_stt_ms / recent_llm_ms /
        # recent_tts_ms are appended in the worker mid-turn, so any
        # read can land between emits — use the min length across all
        # available series to avoid IndexError races. If LLM hasn't
        # recorded yet, we show STT-only bars for this frame, growing
        # into a full stack once more data arrives.
        stt = snapshot.recent_stt_ms
        llm = snapshot.recent_llm_ms
        tts = snapshot.recent_tts_ms
        width = min(len(stt), len(llm)) if stt and llm else 0
        frames = [
            LatencyFrame(
                stt_ms=stt[i],
                llm_ms=llm[i],
                tts_ms=tts[i] if i < len(tts) else 0,
            )
            for i in range(width)
        ]
        self._latency_stack.set_frames(frames)

    def _set_stat(self, key: str, value: str) -> None:
        label = self._stat_labels.get(key)
        if label is not None:
            label.setText(value)

    def _append_log(self, html: str) -> None:
        if self._log_panel is None:
            return
        self._log_panel.append(html)
        bar = self._log_panel.verticalScrollBar()
        bar.setValue(bar.maximum())

    @staticmethod
    def _escape(text: str) -> str:
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            design.global_stylesheet() + """
            QMainWindow { background: transparent; }
            QWidget#windowFrame {
                background-color: rgba(8, 12, 16, 238);
                border: 1px solid rgba(0, 255, 255, 0.22);
                border-radius: 28px;
            }
            QLabel#topTitle {
                color: rgba(210, 240, 255, 0.68);
                font-family: Bahnschrift;
                font-size: 13px;
                letter-spacing: 10px;
                padding-left: 14px;
            }
            QLabel#clockTime {
                color: #eafcff;
                font-family: Consolas;
                font-size: 16px;
                font-weight: 700;
                letter-spacing: 2px;
            }
            QLabel#clockDate {
                color: rgba(125, 230, 240, 0.65);
                font-family: Bahnschrift;
                font-size: 11px;
                letter-spacing: 3px;
            }
            QLabel#centerTitle {
                color: rgba(215, 255, 255, 0.94);
                font-family: Bahnschrift;
                font-size: 38px;
                font-weight: 700;
                letter-spacing: 14px;
                padding-bottom: 4px;
            }
            QFrame#hudPanel {
                background-color: rgba(4, 10, 14, 0.55);
                border: 1px solid rgba(0, 255, 255, 0.2);
                border-radius: 14px;
            }
            QLabel#panelHeader {
                color: rgba(0, 255, 255, 0.75);
                font-family: Bahnschrift;
                font-size: 11px;
                letter-spacing: 6px;
                padding-bottom: 6px;
                border-bottom: 1px solid rgba(0, 255, 255, 0.15);
            }
            QLabel#statName {
                color: rgba(170, 220, 235, 0.72);
                font-family: Bahnschrift;
                font-size: 11px;
                letter-spacing: 3px;
            }
            QLabel#statValue {
                color: #eafcff;
                font-family: Consolas;
                font-size: 15px;
            }
            QLabel#statValueSmall {
                color: #eafcff;
                font-family: Consolas;
                font-size: 12px;
            }
            QLabel#transcriptBanner {
                color: rgba(125, 230, 240, 0.8);
                font-family: Bahnschrift;
                font-size: 15px;
                letter-spacing: 1px;
                padding: 6px 16px;
            }
            QLabel#responseBanner {
                color: #eafcff;
                font-family: Bahnschrift;
                font-size: 17px;
                font-weight: 600;
                letter-spacing: 1px;
                padding: 0 16px 6px 16px;
            }
            QTextEdit#logPanel {
                background-color: rgba(4, 10, 14, 0.85);
                border: 1px solid rgba(0, 255, 255, 0.18);
                border-radius: 14px;
                color: #c9ffff;
                font-family: Consolas;
                font-size: 12px;
                padding: 10px 14px;
                selection-background-color: rgba(0, 255, 255, 0.28);
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
                margin-left: 10px;
            }
            QPushButton#closeButton {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(0, 255, 255, 0.18);
                border-radius: 16px;
                color: #c9ffff;
                font-family: Consolas;
                font-size: 18px;
                /* override the base QPushButton padding (8px/16px) —
                   a 32x32 fixed-size icon button gets its glyph eaten
                   by that padding and renders blank. */
                padding: 0;
            }
            QPushButton#closeButton:hover { background-color: rgba(0, 255, 255, 0.18); }
            QPushButton#settingsButton {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(0, 255, 255, 0.18);
                border-radius: 16px;
                color: #c9ffff;
                font-family: Segoe UI Symbol;
                font-size: 16px;
                padding: 0;
            }
            QPushButton#settingsButton:hover { background-color: rgba(0, 255, 255, 0.18); }
            QFrame#updateBanner {
                background-color: rgba(0, 255, 255, 0.08);
                border: 1px solid rgba(0, 255, 255, 0.35);
                border-radius: 14px;
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

    # ------- drag-to-move (frameless window) -------

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

    # ------- update banner (reused from previous UI) -------

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

        update_button = QPushButton("Update")
        update_button.setObjectName("updateButton")
        update_button.clicked.connect(self._on_update_clicked)
        layout.addWidget(update_button)

        dismiss_button = QPushButton("Later")
        dismiss_button.setObjectName("updateDismissButton")
        dismiss_button.clicked.connect(self.hide_update_banner)
        layout.addWidget(dismiss_button)

        return banner

    def show_update_banner(self, release: ReleaseInfo) -> None:
        if self._update_banner is None or self._update_banner_label is None:
            return
        self._pending_release = release
        summary = (release.body or "").strip().splitlines()
        headline = summary[0] if summary else "New version available."
        self._update_banner_label.setText(
            f"<b>Update available — v{release.version}</b><br/>{headline}"
        )
        self._update_banner.setVisible(True)

    def hide_update_banner(self) -> None:
        if self._update_banner is not None:
            self._update_banner.setVisible(False)

    def _on_update_clicked(self) -> None:
        if self._pending_release is not None:
            self.update_requested.emit(self._pending_release)
        self.hide_update_banner()


def _format_uptime(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def _fmt_ms(ms: int) -> str:
    if not ms:
        return "—"
    if ms >= 10000:
        return f"{ms/1000:.1f}s"
    return f"{ms} ms"
