from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread
from PySide6.QtWidgets import QApplication

from jarvis.interfaces.ispeech_to_text import ISpeechToText
from jarvis.services.assistant_service import AssistantService
from jarvis.services.startup_service import StartupService
from jarvis.ui.events import JarvisEventBus
from jarvis.ui.main_window import MainWindow
from jarvis.ui.worker import AssistantWorker


class ApplicationController(QObject):
    def __init__(
        self,
        qt_app: QApplication,
        speech_to_text: ISpeechToText,
        assistant_service: AssistantService,
        startup_service: StartupService,
        event_bus: JarvisEventBus,
        asset_path: Path,
    ) -> None:
        super().__init__()
        self._qt_app = qt_app
        self._startup_service = startup_service
        self._event_bus = event_bus
        self._window = MainWindow(asset_path=asset_path)
        self._thread = QThread()
        self._worker = AssistantWorker(speech_to_text=speech_to_text, assistant_service=assistant_service)
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
        self._qt_app.aboutToQuit.connect(self.stop)

    def start(self) -> None:
        self._window.show()
        self._thread.start()
        self._startup_service.execute()

    def stop(self) -> None:
        self._worker.stop()
        self._thread.quit()
        self._thread.wait(3000)
