from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Qt, QThread
from PySide6.QtWidgets import QApplication

from jarvis.config.strings import Strings

LOGGER = logging.getLogger(__name__)
from dataclasses import replace

from PySide6.QtWidgets import QDialog, QMessageBox

from jarvis.diagnostics.crash_report import CrashReport
from jarvis.diagnostics.exception_handler import CrashNotifier
from jarvis.diagnostics.issue_reporter import IGitHubIssueReporter
from jarvis.interfaces.ispeech_to_text import ISpeechToText
from jarvis.models.app_settings import AppSettings
from jarvis.services.assistant_service import AssistantService
from jarvis.services.credential_store import (
    ANTHROPIC_API_KEY_USERNAME,
    CredentialStore,
    ELEVENLABS_API_KEY_USERNAME,
    ELEVENLABS_VOICE_ID_USERNAME,
    GEMINI_API_KEY_USERNAME,
    GROQ_API_KEY_USERNAME,
    OPENAI_API_KEY_USERNAME,
    SPOTIFY_CLIENT_ID_USERNAME,
)
from jarvis.services.spotify_auth import SpotifyPkceAuth
from jarvis.services.spotify_controller import SpotifyController
from jarvis.services.spotify_keyboard_controller import SpotifyKeyboardController
from jarvis.services.startup_service import StartupService
from jarvis.services.update_checker import ReleaseInfo
from jarvis.services.update_service import UpdateService
from jarvis.ui.crash_dialog import CrashDialog
from jarvis.ui.events import JarvisEventBus
from jarvis.ui.main_window import MainWindow
from jarvis.ui.settings_dialog import SettingsDialog
from jarvis.ui.stats_collector import StatsCollector
from jarvis.ui.worker import AssistantWorker


class ApplicationController(QObject):
    def __init__(
        self,
        qt_app: QApplication,
        strings: Strings,
        debug: bool,
        speech_to_text: ISpeechToText,
        assistant_service: AssistantService,
        startup_service: StartupService,
        event_bus: JarvisEventBus,
        crash_notifier: CrashNotifier,
        issue_reporter: IGitHubIssueReporter,
        update_service: UpdateService,
        settings: AppSettings,
    ) -> None:
        super().__init__()
        self._qt_app = qt_app
        self._strings = strings
        self._startup_service = startup_service
        self._event_bus = event_bus
        self._crash_notifier = crash_notifier
        self._issue_reporter = issue_reporter
        self._update_service = update_service
        self._settings = settings
        self._assistant_service = assistant_service
        self._credential_store = CredentialStore()
        self._stats = StatsCollector()
        self._window = MainWindow(
            strings=strings, stats=self._stats, debug=debug, settings=settings
        )
        self._thread = QThread()
        self._worker = AssistantWorker(
            strings=strings,
            speech_to_text=speech_to_text,
            assistant_service=assistant_service,
            event_bus=event_bus,
        )
        self._worker.moveToThread(self._thread)
        self._wire_events()

    def _wire_events(self) -> None:
        self._thread.started.connect(self._worker.run)
        self._worker.status_changed.connect(self._window.update_status)
        self._worker.transcript_received.connect(self._window.update_transcript)
        self._worker.response_ready.connect(self._window.update_response)
        self._worker.command_processed.connect(self._window.display_result)
        self._worker.error_occurred.connect(self._window.update_response)
        self._worker.finished.connect(self._thread.quit)
        self._event_bus.speaking_state_changed.connect(self._window.set_speaking)
        self._event_bus.mic_level_changed.connect(self._window.set_mic_level)
        self._event_bus.pipeline_state_changed.connect(self._window.set_state)
        self._event_bus.latency_recorded.connect(self._stats.record_latency)
        self._event_bus.turn_completed.connect(self._stats.record_turn)
        self._event_bus.wake_fired.connect(self._stats.record_wake)
        # Mirror the same events into the HUD's visual event timeline
        # so the user sees activity ripple across the dashboard in
        # real time, not just the numeric counters.
        self._event_bus.turn_completed.connect(self._window.record_turn_event)
        self._event_bus.wake_fired.connect(self._window.record_wake_event)
        self._seed_connection_states()
        self._crash_notifier.crash_occurred.connect(
            self._on_crash_occurred, Qt.ConnectionType.QueuedConnection
        )
        self._update_service.update_available.connect(
            self._on_update_available, Qt.ConnectionType.QueuedConnection
        )
        self._window.update_requested.connect(self._on_update_requested)
        self._window.settings_requested.connect(self._on_settings_requested)
        self._qt_app.aboutToQuit.connect(self.stop)

    def _seed_connection_states(self) -> None:
        """Paint the initial Connections panel from current settings.

        We don't ping each service — the settings fields tell us
        enough to classify "has credentials → ready", "picked + has
        implementation → online", "missing credentials → offline".
        Later the event bus will flip rows as turns land.
        """
        s = self._settings
        # LLM: Groq with a key = online, lm_studio = ready (local),
        # anything else we haven't implemented = offline.
        if s.llm_provider == "groq":
            llm_state = "online" if s.groq_api_key else "offline"
            llm_detail = s.groq_llm_model if s.groq_api_key else "no key"
        elif s.llm_provider == "lm_studio":
            llm_state = "ready"
            llm_detail = s.lm_studio_model
        else:
            llm_state = "offline"
            llm_detail = "coming soon"
        self._window.update_connection_status("llm", llm_state, llm_detail)

        # STT piggybacks on Groq; local Whisper is "ready" always.
        if s.stt_provider == "groq":
            stt_state = "online" if s.groq_api_key else "offline"
            stt_detail = s.groq_stt_model if s.groq_api_key else "no key"
        else:
            stt_state = "ready"
            stt_detail = f"local · {s.whisper_model}"
        self._window.update_connection_status("stt", stt_state, stt_detail)

        # TTS: online when ElevenLabs key is set; otherwise Piper
        # is always ready on disk.
        if s.tts_provider == "elevenlabs":
            tts_state = "online" if s.elevenlabs_api_key else "offline"
            tts_detail = (
                s.elevenlabs_voice_id[:8] if s.elevenlabs_api_key else "no key"
            )
        elif s.tts_provider == "groq":
            tts_state = "warn"
            tts_detail = "deprecated"
        else:
            tts_state = "ready"
            tts_detail = "piper · faber"
        self._window.update_connection_status("tts", tts_state, tts_detail)

        # Wake word and Music are static readouts.
        self._window.update_connection_status(
            "wake", "online" if s.wake_word_enabled else "offline", s.wake_word_model
        )
        if s.music_provider == "spotify":
            music_state = "online" if s.spotify_client_id else "warn"
            music_detail = "api" if s.spotify_client_id else "keyboard fallback"
        else:
            music_state = "offline"
            music_detail = "coming soon"
        self._window.update_connection_status("music", music_state, music_detail)

    def _on_settings_requested(self) -> None:
        try:
            dialog = SettingsDialog(
                parent=self._window,
                llm_provider=self._settings.llm_provider,
                tts_provider=self._settings.tts_provider,
                music_provider=self._settings.music_provider,
                spotify_client_id=self._settings.spotify_client_id,
                groq_api_key=self._settings.groq_api_key,
                elevenlabs_api_key=self._settings.elevenlabs_api_key,
                elevenlabs_voice_id=self._settings.elevenlabs_voice_id,
                openai_api_key=self._settings.openai_api_key,
                anthropic_api_key=self._settings.anthropic_api_key,
                gemini_api_key=self._settings.gemini_api_key,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            # Track whether any saved change needs a restart so we
            # prompt the user once at the end rather than guessing.
            # Spotify hot-swaps cleanly; the other providers rebuild
            # services at boot, so they're what flip this flag.
            needs_restart = False
            self._apply_spotify_change(dialog.spotify_client_id)
            if self._apply_groq_change(dialog.groq_api_key):
                needs_restart = True
            if self._apply_elevenlabs_change(
                dialog.elevenlabs_api_key, dialog.elevenlabs_voice_id
            ):
                needs_restart = True
            if self._apply_cloud_llm_keys(
                openai=dialog.openai_api_key,
                anthropic=dialog.anthropic_api_key,
                gemini=dialog.gemini_api_key,
            ):
                needs_restart = True
            if self._apply_provider_picks(
                llm=dialog.llm_provider,
                tts=dialog.tts_provider,
                music=dialog.music_provider,
            ):
                needs_restart = True
            if needs_restart:
                self._prompt_restart()
        except Exception as exc:
            # Qt swallows exceptions from signal handlers by default; log so
            # settings failures show up in the log file instead of the void.
            LOGGER.exception(
                "settings_apply_failed",
                extra={"event_data": {"error": str(exc)}},
            )

    def _apply_spotify_change(self, new_client_id: str) -> None:
        if new_client_id == self._settings.spotify_client_id:
            return
        # Persist (or clear) in keyring so the next boot picks it up.
        if new_client_id:
            self._credential_store.set(SPOTIFY_CLIENT_ID_USERNAME, new_client_id)
        else:
            self._credential_store.delete(SPOTIFY_CLIENT_ID_USERNAME)
        # Hot-swap the controller so the change takes effect without a restart.
        if new_client_id:
            new_controller = SpotifyController(auth=SpotifyPkceAuth(client_id=new_client_id))
            mode = "api"
        else:
            new_controller = SpotifyKeyboardController()
            mode = "keyboard"
        self._assistant_service.set_spotify_controller(new_controller)
        self._settings = replace(self._settings, spotify_client_id=new_client_id)
        LOGGER.info(
            "spotify_runtime_swap",
            extra={"event_data": {"mode": mode}},
        )

    def _apply_elevenlabs_change(self, new_api_key: str, new_voice_id: str) -> bool:
        """Persist ElevenLabs credentials to keyring. Returns True if
        anything actually changed. No hot-swap — VoiceService is
        mid-synthesis more often than not, and rotating the engine
        while a chunk is in flight risks half-spoken utterances.
        Changes take effect on restart."""
        key_changed = new_api_key != self._settings.elevenlabs_api_key
        voice_changed = new_voice_id != self._settings.elevenlabs_voice_id
        if not key_changed and not voice_changed:
            return False

        if key_changed:
            if new_api_key:
                self._credential_store.set(ELEVENLABS_API_KEY_USERNAME, new_api_key)
            else:
                self._credential_store.delete(ELEVENLABS_API_KEY_USERNAME)

        if voice_changed:
            if new_voice_id:
                self._credential_store.set(
                    ELEVENLABS_VOICE_ID_USERNAME, new_voice_id
                )
            else:
                self._credential_store.delete(ELEVENLABS_VOICE_ID_USERNAME)

        self._settings = replace(
            self._settings,
            elevenlabs_api_key=new_api_key,
            elevenlabs_voice_id=new_voice_id,
        )
        LOGGER.info(
            "elevenlabs_settings_saved",
            extra={
                "event_data": {
                    "has_key": bool(new_api_key),
                    "voice_id": new_voice_id[:8] + "…" if new_voice_id else "",
                    "note": "restart jarvis to apply",
                }
            },
        )
        return True

    def _apply_provider_picks(self, llm: str, tts: str, music: str) -> bool:
        """Persist the provider selections from the settings dialog.
        Returns True if any pick actually changed, so the caller can
        surface a restart prompt once per Save.

        These are simple string fields on AppSettings — no keyring, no
        hot-swap of engines mid-session (rebuilding the LLM/TTS stack
        with a running voice pipeline is a bug surface we'd rather
        avoid).
        """
        changed: dict[str, tuple[str, str]] = {}
        if llm != self._settings.llm_provider:
            changed["llm"] = (self._settings.llm_provider, llm)
        if tts != self._settings.tts_provider:
            changed["tts"] = (self._settings.tts_provider, tts)
        if music != self._settings.music_provider:
            changed["music"] = (self._settings.music_provider, music)
        if not changed:
            return False
        self._settings = replace(
            self._settings,
            llm_provider=llm,
            tts_provider=tts,
            music_provider=music,
        )
        LOGGER.info(
            "provider_picks_saved",
            extra={"event_data": {"changed": changed, "note": "restart jarvis to apply"}},
        )
        return True

    def _apply_groq_change(self, new_api_key: str) -> bool:
        if new_api_key == self._settings.groq_api_key:
            return False
        # Persist in keyring so the next boot picks it up. Unlike Spotify,
        # we don't hot-swap the STT provider — the worker is blocked on
        # audio capture, and rotating a live speech pipeline mid-session
        # is a surface of bugs we'd rather avoid. The UI surfaces a
        # one-time warning on the log instead of trying to be cute.
        if new_api_key:
            self._credential_store.set(GROQ_API_KEY_USERNAME, new_api_key)
        else:
            self._credential_store.delete(GROQ_API_KEY_USERNAME)
        self._settings = replace(self._settings, groq_api_key=new_api_key)
        LOGGER.info(
            "groq_api_key_saved",
            extra={
                "event_data": {
                    "has_key": bool(new_api_key),
                    "note": "restart jarvis to apply",
                }
            },
        )
        return True

    def _apply_cloud_llm_keys(
        self, *, openai: str, anthropic: str, gemini: str
    ) -> bool:
        """Persist the cloud LLM API keys via keyring. Mirrors the
        per-provider apply methods: returns True when at least one
        value actually changed so the caller prompts for a restart.
        These keys aren't hot-swappable because LocalLLM is built
        once at boot around a single backend service."""
        changes = 0
        for key_name, new_value, current, storage_key in (
            (
                "openai",
                openai,
                self._settings.openai_api_key,
                OPENAI_API_KEY_USERNAME,
            ),
            (
                "anthropic",
                anthropic,
                self._settings.anthropic_api_key,
                ANTHROPIC_API_KEY_USERNAME,
            ),
            (
                "gemini",
                gemini,
                self._settings.gemini_api_key,
                GEMINI_API_KEY_USERNAME,
            ),
        ):
            if new_value == current:
                continue
            changes += 1
            if new_value:
                self._credential_store.set(storage_key, new_value)
            else:
                self._credential_store.delete(storage_key)

        if changes == 0:
            return False
        self._settings = replace(
            self._settings,
            openai_api_key=openai,
            anthropic_api_key=anthropic,
            gemini_api_key=gemini,
        )
        LOGGER.info(
            "cloud_llm_keys_saved",
            extra={
                "event_data": {
                    "has_openai": bool(openai),
                    "has_anthropic": bool(anthropic),
                    "has_gemini": bool(gemini),
                    "note": "restart jarvis to apply",
                }
            },
        )
        return True

    def _prompt_restart(self) -> None:
        """Show a modal telling the user the save landed but a restart
        is needed for voice/LLM providers to rebuild. Keeps the user
        from thinking the save silently failed."""
        box = QMessageBox(self._window)
        box.setWindowTitle("Restart required")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText("Settings saved.")
        box.setInformativeText(
            "Close and reopen Jarvis for the new voice, AI or music "
            "provider to take effect. The audio pipeline can't hot-swap "
            "engines while it's running."
        )
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()

    def _on_crash_occurred(self, report: CrashReport) -> None:
        dialog = CrashDialog(report=report, issue_reporter=self._issue_reporter, parent=self._window)
        dialog.exec()

    def _on_update_available(self, release: ReleaseInfo) -> None:
        self._window.show_update_banner(release)

    def _on_update_requested(self, release: ReleaseInfo) -> None:
        self._update_service.apply_async(release)

    def start(self) -> None:
        self._window.show()
        self._thread.start()
        self._startup_service.execute()
        self._update_service.check_async()

    def stop(self) -> None:
        self._worker.stop()
        self._thread.quit()
        self._thread.wait(3000)
