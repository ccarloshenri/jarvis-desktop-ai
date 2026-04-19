from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from PySide6.QtWidgets import QApplication

from jarvis.apps.browser.browser_app import BrowserApp
from jarvis.apps.browser.browser_controller import BrowserController
from jarvis.apps.discord.discord_app import DiscordApp
from jarvis.apps.discord.discord_keyboard_controller import DiscordKeyboardController
from jarvis.config.settings_loader import SettingsLoader
from jarvis.config.strings import Strings
from jarvis.diagnostics.bundle import Diagnostics, build_diagnostics
from jarvis.implementations.llm.local_llm import LocalLLM
from jarvis.implementations.stt.audio_capture import AudioCapture
from jarvis.implementations.stt.google_stt_provider import GoogleSTTProvider
from jarvis.implementations.stt.groq_stt_provider import GroqSTTProvider
from jarvis.implementations.stt.stt_service import STTService
from jarvis.implementations.stt.vad_silero import SileroVAD, SileroVadUnavailableError
from jarvis.implementations.stt.wake_word_audio_capture import WakeWordAudioCapture
from jarvis.implementations.stt.wake_word_detector import (
    WakeWordDetector,
    WakeWordUnavailableError,
)
from jarvis.implementations.stt.whisper_stt_provider import WhisperSTTProvider
from jarvis.interfaces.iaudio_capture import IAudioCapture
from jarvis.implementations.system.system_action_executor import SystemActionExecutor
from jarvis.implementations.system.windows_application_finder import WindowsApplicationFinder
from jarvis.implementations.tts.offline_tts import OfflineTTS
from jarvis.interfaces.illm import ILLM
from jarvis.interfaces.istt_provider import ISTTProvider
from jarvis.interfaces.itext_to_speech import ITextToSpeech
from jarvis.models.app_settings import AppSettings
from jarvis.services.assistant_service import AssistantService
from jarvis.services.audio_player import AudioPlayer
from jarvis.services.context_aware_correction_service import (
    ContextAwareCorrectionService,
)
from jarvis.services.conversation_memory import ConversationMemory
from jarvis.services.entity_resolvers.app_entity_resolver import AppEntityResolver
from jarvis.services.entity_resolvers.spotify_entity_resolver import (
    SpotifyEntityResolver,
)
from jarvis.services.lmstudio_service import LMStudioService
from jarvis.services.spotify_auth import SpotifyPkceAuth
from jarvis.services.spotify_controller import SpotifyController
from jarvis.services.spotify_keyboard_controller import SpotifyKeyboardController
from jarvis.services.startup_service import StartupService
from jarvis.services.tts_cache import TtsCache
from jarvis.services.elevenlabs_tts_engine import ElevenLabsTTSEngine
from jarvis.services.groq_tts_engine import GroqTTSEngine
from jarvis.services.tts_engine import PiperEngine, PrewarmedPiperEngine, TtsEngineError
from jarvis.services.wake_sound import play_wake_chime
from jarvis.services.update_checker import UpdateChecker
from jarvis.services.update_service import UpdateService
from jarvis.services.updater import Updater
from jarvis.services.voice_service import VoiceService
from jarvis.ui.application_controller import ApplicationController
from jarvis.ui.events import JarvisEventBus
from jarvis.utils.command_mapper import CommandMapper

LOGGER = logging.getLogger(__name__)


class ApplicationFactory:
    def __init__(self, project_root: Path, diagnostics: Diagnostics | None = None) -> None:
        self._project_root = project_root
        self._diagnostics = diagnostics or build_diagnostics(project_root)

    def create(self, qt_app: QApplication) -> ApplicationController:
        settings = SettingsLoader(self._project_root).load()
        strings = Strings(language=settings.language)
        self._diagnostics.crash_context.set_provider("local")
        event_bus = JarvisEventBus()
        llm = self._create_llm(settings)
        # Application finder created early so we can (a) pass it to the
        # STT provider for dynamic vocabulary and (b) hand it to the app
        # entity resolver for context-aware target validation.
        application_finder = WindowsApplicationFinder()
        speech_to_text = self._create_stt(settings, application_finder, event_bus)
        text_to_speech = self._create_tts(settings, event_bus)
        spotify_controller = self._create_spotify_controller(settings.spotify_client_id)
        discord_app = DiscordApp(controller=DiscordKeyboardController())
        browser_app = BrowserApp(controller=BrowserController())
        correction_service = self._create_correction_service(
            application_finder, spotify_controller
        )
        assistant_service = AssistantService(
            strings=strings,
            action_executor=SystemActionExecutor(
                application_finder,
                spotify_controller=spotify_controller,
                apps=[browser_app, discord_app],
            ),
            llm=llm,
            text_to_speech=text_to_speech,
            command_mapper=CommandMapper(),
            conversation_memory=ConversationMemory(
                max_turns=10,
                # Persist to the user's AppData folder so context
                # survives restarts. Not committed, per-user, cleared
                # by a Windows user switch.
                persistence_path=self._project_root / "data" / "conversation_memory.json",
            ),
            correction_service=correction_service,
            llm_streaming=settings.llm_streaming,
        )
        startup_service = StartupService(
            strings=strings,
            text_to_speech=text_to_speech,
            prefetch=application_finder.prefetch,
        )
        update_service = UpdateService(
            checker=UpdateChecker(
                repo=self._diagnostics.github_repo,
                current_version=self._diagnostics.app_version,
            ),
            updater=Updater(),
        )
        return ApplicationController(
            qt_app=qt_app,
            strings=strings,
            debug=settings.debug,
            speech_to_text=speech_to_text,
            assistant_service=assistant_service,
            startup_service=startup_service,
            event_bus=event_bus,
            crash_notifier=self._diagnostics.notifier,
            issue_reporter=self._diagnostics.issue_reporter,
            update_service=update_service,
            settings=settings,
        )

    def _create_llm(self, settings: AppSettings) -> ILLM:
        """Build the LLM backend from settings.

        Five providers supported — all implementing the same
        `chat()` / `chat_stream()` contract so `LocalLLM` doesn't
        care which one is behind it:

        - groq        → OpenAI-compatible (LMStudioService, cloud)
        - openai      → OpenAI-compatible (LMStudioService, api.openai)
        - gemini      → Google's OpenAI-compat endpoint
                        (generativelanguage.googleapis.com/...openai/)
        - anthropic   → native Messages API via AnthropicService
        - lm_studio   → local OpenAI-compatible (LMStudioService)

        Missing credential → fall back to LM Studio (local). The log
        line tells the user exactly what happened so they can fix it.
        """
        provider = (settings.llm_provider or "lm_studio").lower()
        service, provider_label = self._build_llm_service(settings, provider)

        reachable = service.ping()
        LOGGER.info(
            "llm_backend_selected",
            extra={
                "event_data": {
                    "provider": provider_label,
                    "reachable": reachable,
                    "url": service.base_url,
                    "model": service.model,
                }
            },
        )
        if not reachable:
            LOGGER.warning(
                "llm_backend_not_reachable_at_boot",
                extra={"event_data": {"provider": provider_label, "url": service.base_url}},
            )
        return LocalLLM(service=service)

    def _build_llm_service(
        self, settings: AppSettings, provider: str
    ) -> tuple[object, str]:
        """Return (service, resolved_provider_label) for the picked
        provider, falling back to LM Studio when credentials are
        missing. Split out so _create_llm stays readable and each
        provider branch is a single obvious block."""
        from jarvis.services.anthropic_service import AnthropicService

        if provider == "groq" and settings.groq_api_key:
            return (
                LMStudioService(
                    base_url="https://api.groq.com/openai/v1",
                    model=settings.groq_llm_model,
                    api_key=settings.groq_api_key,
                ),
                "groq",
            )
        if provider == "openai" and settings.openai_api_key:
            return (
                LMStudioService(
                    base_url="https://api.openai.com/v1",
                    model=settings.openai_model,
                    api_key=settings.openai_api_key,
                ),
                "openai",
            )
        if provider == "gemini" and settings.gemini_api_key:
            # Google exposes an OpenAI-compat endpoint for Gemini —
            # lets us reuse the same streaming client the other
            # OpenAI-compat providers go through.
            return (
                LMStudioService(
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                    model=settings.gemini_model,
                    api_key=settings.gemini_api_key,
                ),
                "gemini",
            )
        if provider == "anthropic" and settings.anthropic_api_key:
            return (
                AnthropicService(
                    api_key=settings.anthropic_api_key,
                    model=settings.anthropic_model,
                ),
                "anthropic",
            )

        # Any branch that didn't return above falls through to LM
        # Studio. Log *why* so the user can trace it.
        if provider != "lm_studio":
            LOGGER.warning(
                "llm_backend_missing_credentials_fallback",
                extra={
                    "event_data": {
                        "requested": provider,
                        "fallback": "lm_studio",
                        "hint": "set the provider's api key via the settings dialog",
                    }
                },
            )
        return (
            LMStudioService(
                base_url=settings.lm_studio_url,
                model=settings.lm_studio_model,
            ),
            "lm_studio",
        )

    def _create_spotify_controller(self, client_id: str) -> SpotifyController | SpotifyKeyboardController:
        if client_id:
            LOGGER.info("spotify_controller_selected", extra={"event_data": {"mode": "api"}})
            return SpotifyController(auth=SpotifyPkceAuth(client_id=client_id))
        LOGGER.info("spotify_controller_selected", extra={"event_data": {"mode": "keyboard"}})
        return SpotifyKeyboardController()

    def _create_stt(
        self,
        settings: AppSettings,
        application_finder: WindowsApplicationFinder,
        event_bus: JarvisEventBus,
    ) -> STTService:
        provider = self._create_stt_provider(settings, application_finder)
        audio_capture = self._create_audio_capture(settings, event_bus)
        LOGGER.info(
            "stt_provider_selected",
            extra={
                "event_data": {
                    "provider": provider.name,
                    "language": settings.language,
                    "capture": type(audio_capture).__name__,
                }
            },
        )
        return STTService(audio_capture=audio_capture, provider=provider, language=settings.language)

    def _create_audio_capture(
        self, settings: AppSettings, event_bus: JarvisEventBus
    ) -> IAudioCapture:
        # Wake-word capture is the fast path: continuous low-cost detection
        # avoids running Whisper on ambient room noise. We try to warm the
        # detector here so a missing model / missing dep falls back at boot
        # rather than blowing up the worker thread on the first listen().
        if not settings.wake_word_enabled:
            LOGGER.info("wake_word_disabled_by_setting")
            return AudioCapture()
        detector = WakeWordDetector(
            model_name=settings.wake_word_model,
            threshold=settings.wake_word_threshold,
            debug_scores=settings.wake_word_debug,
        )
        try:
            detector.warmup()
        except WakeWordUnavailableError as exc:
            LOGGER.warning(
                "wake_word_unavailable_falling_back",
                extra={"event_data": {"error": str(exc)}},
            )
            return AudioCapture()
        dump_dir = self._resolve_audio_dump_dir()
        vad = self._create_vad(settings)
        LOGGER.info(
            "wake_word_enabled",
            extra={
                "event_data": {
                    "model": settings.wake_word_model,
                    "threshold": settings.wake_word_threshold,
                    "dump_dir": str(dump_dir) if dump_dir else None,
                    "vad": "silero" if vad is not None else "rms",
                }
            },
        )
        # `wake_fired` is a new event-bus signal the HUD listens on to
        # bump its wake-fires counter. We also fire a short audible
        # "pim" so the user gets immediate feedback that Jarvis heard
        # them, even before the STT round-trip finishes. Both run from
        # a single callback so the capture class stays decoupled from
        # both the event bus and the sound subsystem.
        def _on_wake() -> None:
            play_wake_chime()
            event_bus.emit_wake_fired()

        return WakeWordAudioCapture(
            detector=detector,
            vad=vad,
            dump_dir=dump_dir,
            level_callback=event_bus.emit_mic_level,
            wake_callback=_on_wake,
            vad_silence_end_seconds=settings.vad_silence_end_seconds,
            vad_min_command_seconds=settings.vad_min_command_seconds,
        )

    def _create_vad(self, settings: AppSettings) -> SileroVAD | None:
        """Build a Silero VAD instance if enabled and the model is available.

        Returns None when the user has explicitly selected the RMS backend
        or when the ONNX model / runtime isn't present — the capture then
        uses the legacy RMS silence heuristic without failing at boot.
        """
        if settings.vad_backend != "silero":
            return None
        model_path = self._resolve_silero_vad_path()
        if model_path is None:
            LOGGER.warning(
                "silero_vad_model_missing_falling_back_to_rms",
                extra={"event_data": {"expected": str(self._project_root / "models" / "vad")}},
            )
            return None
        vad = SileroVAD(model_path=model_path, threshold=settings.vad_threshold)
        try:
            vad.warmup()
        except SileroVadUnavailableError as exc:
            LOGGER.warning(
                "silero_vad_warmup_failed_falling_back_to_rms",
                extra={"event_data": {"error": str(exc)}},
            )
            return None
        return vad

    def _resolve_silero_vad_path(self) -> Path | None:
        env_path = os.environ.get("JARVIS_SILERO_VAD_MODEL", "").strip()
        if env_path:
            candidate = Path(env_path)
            if candidate.exists():
                return candidate
        default = self._project_root / "models" / "vad" / "silero_vad.onnx"
        if default.exists():
            return default
        return None

    def _resolve_audio_dump_dir(self) -> Path | None:
        raw = os.environ.get("JARVIS_AUDIO_DUMP_DIR", "").strip()
        if raw.lower() in {"off", "none", "false", "0"}:
            return None
        if not raw:
            # Default-on: write every captured utterance to logs/audio_dumps/
            # so the user can compare what Whisper heard against the
            # transcript when one comes back garbled. Turn off with
            # JARVIS_AUDIO_DUMP_DIR=off if the disk churn isn't wanted.
            return self._project_root / "logs" / "audio_dumps"
        path = Path(raw)
        if not path.is_absolute():
            path = self._project_root / path
        return path

    def _create_stt_provider(
        self, settings: AppSettings, application_finder: WindowsApplicationFinder
    ) -> ISTTProvider:
        preference = (settings.stt_provider or "whisper").lower()
        if preference == "groq":
            if not settings.groq_api_key:
                LOGGER.warning(
                    "groq_stt_no_api_key_falling_back_to_whisper",
                    extra={"event_data": {"hint": "set GROQ_API_KEY in .env"}},
                )
            else:
                LOGGER.info(
                    "stt_provider_selected_groq",
                    extra={"event_data": {"model": settings.groq_stt_model}},
                )
                return GroqSTTProvider(
                    api_key=settings.groq_api_key,
                    model=settings.groq_stt_model,
                )
        if preference == "google":
            return GoogleSTTProvider()
        try:
            import faster_whisper  # noqa: F401
        except ImportError as exc:
            LOGGER.warning(
                "whisper_unavailable_fallback_google",
                extra={"event_data": {"error": str(exc)}},
            )
            return GoogleSTTProvider()
        provider = WhisperSTTProvider(
            model_size=settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            beam_size=settings.whisper_beam_size,
        )
        try:
            provider.warmup()
        except Exception as exc:
            LOGGER.warning(
                "whisper_warmup_failed_fallback_google",
                extra={"event_data": {"error": str(exc)}},
            )
            return GoogleSTTProvider()
        # Feed installed-app names into Whisper's decoder prompt off the
        # main thread: scanning Start Menu paths can take 500ms-2s on a
        # cold boot, and we don't want to block the UI. The first few
        # utterances might miss the dynamic vocabulary if they land before
        # this completes, which is fine — the base prompt is still there.
        threading.Thread(
            target=_feed_whisper_vocabulary,
            args=(provider, application_finder),
            name="jarvis-whisper-vocab",
            daemon=True,
        ).start()
        return provider

    def _create_correction_service(
        self,
        application_finder: WindowsApplicationFinder,
        spotify_controller: SpotifyController | SpotifyKeyboardController,
    ) -> ContextAwareCorrectionService:
        resolvers = [AppEntityResolver(application_finder=application_finder)]
        # Only the real Spotify API controller can search; the keyboard
        # fallback has no catalog access. Skip the resolver in keyboard
        # mode so we never attempt a correction we can't back with data.
        if isinstance(spotify_controller, SpotifyController):
            resolvers.append(SpotifyEntityResolver(controller=spotify_controller))
        return ContextAwareCorrectionService(resolvers=resolvers)

    def _create_tts(self, settings: AppSettings, event_bus: JarvisEventBus) -> ITextToSpeech:
        fallback = OfflineTTS(speech_events=event_bus, language=settings.language)

        engine = self._create_tts_engine(settings, fallback, event_bus)
        if engine is None:
            return fallback

        player = AudioPlayer()
        cache = TtsCache()
        voice = VoiceService(
            engine=engine,
            player=player,
            cache=cache,
            speech_events=event_bus,
            fallback=fallback,
        )
        voice.start()
        # Pre-warm common phrases off the main thread — the cache query in
        # VoiceService is safe against partial warms, so any phrase that
        # hasn't been synthesized yet just falls through to live synthesis.
        threading.Thread(
            target=cache.warm,
            args=(engine,),
            name="jarvis-tts-cache-warmup",
            daemon=True,
        ).start()
        return voice

    def _create_tts_engine(
        self,
        settings: AppSettings,
        fallback: ITextToSpeech,
        event_bus: JarvisEventBus,
    ) -> object | None:
        """Pick a TTS engine, or None to signal the caller to drop back
        to the OfflineTTS fallback.

        Provider preference order (from most natural to least):
        elevenlabs → groq → piper. Important: when the user opted into
        cloud TTS (elevenlabs/groq) and it's unavailable, we fall to
        the OTHER cloud option before Piper — Piper's only installed
        model is pt_BR-faber, so with JARVIS_LANGUAGE=en-US falling to
        Piper produces a Portuguese voice reading English phonemes,
        which is worse than any cloud option.
        """
        language_is_pt = settings.language.lower().startswith("pt")

        if settings.tts_provider == "elevenlabs":
            engine = self._try_elevenlabs(settings)
            if engine is not None:
                return engine
            # ElevenLabs unavailable — no Groq fallback. Groq's playai-tts
            # was decommissioned upstream (HTTP 400 on every call) so
            # routing here would 100% fail. Dropping to the OfflineTTS
            # (SAPI David) via return None gets at least an English
            # voice out while the user configures ElevenLabs.

        if settings.tts_provider == "groq":
            LOGGER.warning(
                "groq_tts_decommissioned",
                extra={
                    "event_data": {
                        "note": "playai-tts is no longer available upstream; "
                        "use elevenlabs or piper"
                    }
                },
            )

        # Piper's installed model is Portuguese — skip it when the user
        # is running an English session, falling straight to the
        # OfflineTTS (SAPI David) which is at least English. Speaking
        # English phonemes through a PT voice sounded horrendous.
        if not language_is_pt:
            LOGGER.warning(
                "piper_skipped_language_mismatch",
                extra={"event_data": {"language": settings.language}},
            )
            return None

        piper_exe = self._resolve_piper_exe()
        model_path = self._resolve_voice_model_path()
        if piper_exe is None or model_path is None:
            LOGGER.info(
                "tts_engine_selected",
                extra={
                    "event_data": {
                        "engine": "sapi5",
                        "piper_exe_found": piper_exe is not None,
                        "model_found": model_path is not None,
                    }
                },
            )
            return None

        length_scale = _env_float("JARVIS_TTS_LENGTH_SCALE", 1.1)
        sentence_silence_s = _env_float("JARVIS_TTS_SENTENCE_SILENCE", 0.3)
        noise_scale = _env_float("JARVIS_TTS_NOISE_SCALE", 0.5)
        noise_w = _env_float("JARVIS_TTS_NOISE_W", 0.7)
        try:
            if settings.piper_persistent:
                engine = PrewarmedPiperEngine(
                    piper_exe=piper_exe,
                    model_path=model_path,
                    length_scale=length_scale,
                    sentence_silence_s=sentence_silence_s,
                    noise_scale=noise_scale,
                    noise_w=noise_w,
                )
            else:
                engine = PiperEngine(
                    piper_exe=piper_exe,
                    model_path=model_path,
                    length_scale=length_scale,
                    sentence_silence_s=sentence_silence_s,
                    noise_scale=noise_scale,
                    noise_w=noise_w,
                )
        except TtsEngineError as exc:
            LOGGER.warning(
                "voice_service_unavailable",
                extra={"event_data": {"error": str(exc)}},
            )
            return None

        LOGGER.info(
            "tts_engine_selected",
            extra={
                "event_data": {
                    "engine": "piper",
                    "mode": "prewarmed" if settings.piper_persistent else "spawn-per-chunk",
                    "exe": str(piper_exe),
                    "model": str(model_path),
                    "sample_rate": engine.sample_rate,
                }
            },
        )
        return engine

    def _try_elevenlabs(self, settings: AppSettings) -> object | None:
        if not settings.elevenlabs_api_key:
            LOGGER.warning(
                "elevenlabs_no_api_key_falling_back",
                extra={"event_data": {"hint": "set ELEVENLABS_API_KEY"}},
            )
            return None
        try:
            engine = ElevenLabsTTSEngine(
                api_key=settings.elevenlabs_api_key,
                voice_id=settings.elevenlabs_voice_id,
                model=settings.elevenlabs_model,
            )
        except TtsEngineError as exc:
            LOGGER.warning(
                "elevenlabs_engine_init_failed",
                extra={"event_data": {"error": str(exc)}},
            )
            return None
        LOGGER.info(
            "tts_engine_selected",
            extra={
                "event_data": {
                    "engine": "elevenlabs",
                    "voice_id": settings.elevenlabs_voice_id,
                    "model": settings.elevenlabs_model,
                }
            },
        )
        return engine

    def _try_groq_tts(self, settings: AppSettings) -> object | None:
        if not settings.groq_api_key:
            LOGGER.warning(
                "groq_tts_no_api_key_falling_back",
                extra={"event_data": {"hint": "set GROQ_API_KEY"}},
            )
            return None
        try:
            engine = GroqTTSEngine(
                api_key=settings.groq_api_key,
                model=settings.groq_tts_model,
                voice=settings.groq_tts_voice,
            )
        except TtsEngineError as exc:
            LOGGER.warning(
                "groq_tts_engine_init_failed",
                extra={"event_data": {"error": str(exc)}},
            )
            return None
        LOGGER.info(
            "tts_engine_selected",
            extra={
                "event_data": {
                    "engine": "groq",
                    "model": settings.groq_tts_model,
                    "voice": settings.groq_tts_voice,
                }
            },
        )
        return engine

    def _resolve_piper_exe(self) -> Path | None:
        env_path = os.environ.get("JARVIS_PIPER_EXE", "").strip()
        if env_path:
            candidate = Path(env_path)
            if candidate.exists():
                return candidate
        default = self._project_root / "tools" / "piper" / "piper.exe"
        if default.exists():
            return default
        return None

    def _resolve_voice_model_path(self) -> Path | None:
        env_path = os.environ.get("JARVIS_VOICE_MODEL", "").strip()
        if env_path:
            candidate = Path(env_path)
            if candidate.exists():
                return candidate
        default = self._project_root / "models" / "piper" / "pt_BR-faber-medium.onnx"
        if default.exists():
            return default
        return None


def _feed_whisper_vocabulary(
    provider: WhisperSTTProvider,
    application_finder: WindowsApplicationFinder,
) -> None:
    """Pulls installed-app names from the finder and hands them to the
    Whisper provider as decoder vocabulary. Runs once at boot.

    Deduping and length bounds live inside set_vocabulary, so we can
    pass the raw candidate list; the provider decides how much fits.
    """
    try:
        candidates = application_finder.candidates()
    except Exception:
        LOGGER.exception("whisper_vocab_scan_failed")
        return
    names = [c.name for c in candidates]
    provider.set_vocabulary(names)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        LOGGER.warning(
            "env_float_parse_failed",
            extra={"event_data": {"name": name, "value": raw, "default": default}},
        )
        return default
