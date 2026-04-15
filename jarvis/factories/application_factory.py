from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from jarvis.config.settings_loader import SettingsLoader
from jarvis.factories.llm_factory import LLMFactory
from jarvis.implementations.audio.pygame_audio_player import PygameAudioPlayer
from jarvis.implementations.llm.rule_based_command_interpreter import RuleBasedCommandInterpreter
from jarvis.implementations.speech.speech_recognition_service import SpeechRecognitionService
from jarvis.implementations.system.system_action_executor import SystemActionExecutor
from jarvis.implementations.system.windows_application_finder import WindowsApplicationFinder
from jarvis.implementations.tts.offline_tts import OfflineTTS
from jarvis.services.audio_feedback_service import AudioFeedbackService
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
        event_bus = JarvisEventBus()
        llm = LLMFactory(settings).create()
        speech_to_text = SpeechRecognitionService()
        text_to_speech = OfflineTTS(speech_events=event_bus)
        audio_player = PygameAudioPlayer(speech_events=event_bus)
        audio_feedback = AudioFeedbackService(
            audio_player=audio_player,
            startup_audio_path=settings.startup_audio_path,
            success_audio_path=settings.success_audio_path,
        )
        assistant_service = AssistantService(
            local_intent_handler=LocalIntentHandler(),
            command_interpreter=RuleBasedCommandInterpreter(),
            action_executor=SystemActionExecutor(WindowsApplicationFinder()),
            llm=llm,
            text_to_speech=text_to_speech,
            audio_feedback=audio_feedback,
            command_mapper=CommandMapper(),
        )
        startup_service = StartupService(audio_feedback=audio_feedback)
        return ApplicationController(
            qt_app=qt_app,
            speech_to_text=speech_to_text,
            assistant_service=assistant_service,
            startup_service=startup_service,
            event_bus=event_bus,
            asset_path=settings.asset_path,
        )
