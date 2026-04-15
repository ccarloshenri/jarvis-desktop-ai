from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from jarvis.config.settings_loader import SettingsLoader
from jarvis.config.strings import Strings
from jarvis.factories.llm_factory import LLMFactory
from jarvis.implementations.llm.rule_based_command_interpreter import RuleBasedCommandInterpreter
from jarvis.implementations.speech.speech_recognition_service import SpeechRecognitionService
from jarvis.implementations.system.system_action_executor import SystemActionExecutor
from jarvis.implementations.system.windows_application_finder import WindowsApplicationFinder
from jarvis.implementations.tts.offline_tts import OfflineTTS
from jarvis.services.assistant_service import AssistantService
from jarvis.services.local_intent_handler import LocalIntentHandler
from jarvis.services.startup_service import StartupService
from jarvis.ui.application_controller import ApplicationController
from jarvis.ui.events import JarvisEventBus
from jarvis.utils.command_mapper import CommandMapper


class ApplicationFactory:
    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root

    def create(self, qt_app: QApplication) -> ApplicationController:
        settings = SettingsLoader(self._project_root).load()
        strings = Strings(language=settings.language)
        event_bus = JarvisEventBus()
        llm = LLMFactory(settings, strings).create()
        speech_to_text = SpeechRecognitionService()
        text_to_speech = OfflineTTS(speech_events=event_bus, language=settings.language)
        assistant_service = AssistantService(
            strings=strings,
            local_intent_handler=LocalIntentHandler(strings=strings),
            command_interpreter=RuleBasedCommandInterpreter(),
            action_executor=SystemActionExecutor(WindowsApplicationFinder()),
            llm=llm,
            text_to_speech=text_to_speech,
            command_mapper=CommandMapper(),
        )
        startup_service = StartupService(strings=strings, text_to_speech=text_to_speech)
        return ApplicationController(
            qt_app=qt_app,
            strings=strings,
            debug=settings.debug,
            speech_to_text=speech_to_text,
            assistant_service=assistant_service,
            startup_service=startup_service,
            event_bus=event_bus,
        )
