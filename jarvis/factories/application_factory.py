from __future__ import annotations

import logging
import os
from pathlib import Path

from PySide6.QtWidgets import QApplication

from jarvis.apps.browser.browser_app import BrowserApp
from jarvis.apps.browser.browser_controller import BrowserController
from jarvis.apps.discord.discord_app import DiscordApp
from jarvis.apps.discord.discord_keyboard_controller import DiscordKeyboardController
from jarvis.config.settings_loader import SettingsLoader
from jarvis.config.strings import Strings
from jarvis.diagnostics.bundle import Diagnostics, build_diagnostics
from jarvis.factories.llm_factory import LLMFactory
from jarvis.services.provider_setup_service import ProviderSetupService
from jarvis.implementations.llm.rule_based_command_interpreter import RuleBasedCommandInterpreter
from jarvis.implementations.speech.speech_recognition_service import SpeechRecognitionService
from jarvis.implementations.system.system_action_executor import SystemActionExecutor
from jarvis.implementations.system.windows_application_finder import WindowsApplicationFinder
from jarvis.implementations.tts.offline_tts import OfflineTTS
from jarvis.interfaces.itext_to_speech import ITextToSpeech
from jarvis.services.assistant_service import AssistantService
from jarvis.services.conversation_memory import ConversationMemory
from jarvis.services.local_intent_handler import LocalIntentHandler
from jarvis.services.spotify_keyboard_controller import SpotifyKeyboardController
from jarvis.services.startup_service import StartupService
from jarvis.services.update_checker import UpdateChecker
from jarvis.services.update_service import UpdateService
from jarvis.services.updater import Updater
from jarvis.services.voice_service import VoiceService, VoiceServiceError
from jarvis.ui.application_controller import ApplicationController
from jarvis.ui.events import JarvisEventBus
from jarvis.utils.command_mapper import CommandMapper

LOGGER = logging.getLogger(__name__)


class ApplicationFactory:
    def __init__(self, project_root: Path, diagnostics: Diagnostics | None = None) -> None:
        self._project_root = project_root
        self._diagnostics = diagnostics or build_diagnostics(project_root)

    def create(self, qt_app: QApplication) -> ApplicationController:
        env_settings = SettingsLoader(self._project_root).load()
        strings = Strings(language=env_settings.language)
        provider_setup = ProviderSetupService()
        settings = provider_setup.bootstrap_settings(env_settings)
        self._diagnostics.crash_context.set_provider(settings.llm_provider.value)
        event_bus = JarvisEventBus()
        llm_factory = LLMFactory(settings, strings)
        llm = llm_factory.create()
        speech_to_text = SpeechRecognitionService(language=settings.language)
        text_to_speech = self._create_tts(settings.language, event_bus)
        application_finder = WindowsApplicationFinder()
        spotify_controller = SpotifyKeyboardController()
        discord_app = DiscordApp(controller=DiscordKeyboardController())
        browser_app = BrowserApp(controller=BrowserController())
        assistant_service = AssistantService(
            strings=strings,
            local_intent_handler=LocalIntentHandler(strings=strings),
            command_interpreter=RuleBasedCommandInterpreter(),
            action_executor=SystemActionExecutor(
                application_finder,
                spotify_controller=spotify_controller,
                apps=[browser_app, discord_app],
            ),
            llm=llm,
            text_to_speech=text_to_speech,
            command_mapper=CommandMapper(),
            conversation_memory=ConversationMemory(max_turns=10),
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
            provider_setup=provider_setup,
            env_settings=env_settings,
            llm_factory=llm_factory,
            settings=settings,
        )

    def _create_tts(self, language: str, event_bus: JarvisEventBus) -> ITextToSpeech:
        piper_exe = self._resolve_piper_exe()
        model_path = self._resolve_voice_model_path()
        if piper_exe is not None and model_path is not None:
            try:
                voice = VoiceService(
                    piper_exe=piper_exe,
                    model_path=model_path,
                    speech_events=event_bus,
                    language=language,
                )
                LOGGER.info(
                    "tts_engine_selected",
                    extra={"event_data": {"engine": "piper", "exe": str(piper_exe), "model": str(model_path)}},
                )
                return voice
            except VoiceServiceError as exc:
                LOGGER.warning(
                    "voice_service_unavailable",
                    extra={"event_data": {"error": str(exc)}},
                )
        LOGGER.info(
            "tts_engine_selected",
            extra={"event_data": {"engine": "sapi5", "piper_exe_found": piper_exe is not None, "model_found": model_path is not None}},
        )
        return OfflineTTS(speech_events=event_bus, language=language)

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
