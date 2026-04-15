from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QThread
from PySide6.QtWidgets import QApplication

from jarvis.config.strings import Strings
from jarvis.diagnostics.crash_report import CrashReport
from jarvis.diagnostics.exception_handler import CrashNotifier
from jarvis.diagnostics.issue_reporter import IGitHubIssueReporter
from jarvis.factories.llm_factory import LLMFactory
from jarvis.interfaces.ispeech_to_text import ISpeechToText
from jarvis.models.app_settings import AppSettings
from jarvis.services.assistant_service import AssistantService
from jarvis.services.provider_setup_service import ProviderSetupService
from jarvis.services.startup_service import StartupService
from jarvis.services.update_checker import ReleaseInfo
from jarvis.services.update_service import UpdateService
from jarvis.ui.crash_dialog import CrashDialog
from jarvis.ui.events import JarvisEventBus
from jarvis.ui.main_window import MainWindow
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
        provider_setup: ProviderSetupService,
        env_settings: AppSettings,
        llm_factory: LLMFactory,
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
        self._provider_setup = provider_setup
        self._env_settings = env_settings
        self._current_settings = settings
        self._llm_factory = llm_factory
        self._assistant_service = assistant_service
        self._window = MainWindow(strings=strings, debug=debug)
        self._thread = QThread()
        self._worker = AssistantWorker(
            strings=strings,
            speech_to_text=speech_to_text,
            assistant_service=assistant_service,
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
        self._crash_notifier.crash_occurred.connect(
            self._on_crash_occurred, Qt.ConnectionType.QueuedConnection
        )
        self._update_service.update_available.connect(
            self._on_update_available, Qt.ConnectionType.QueuedConnection
        )
        self._window.update_requested.connect(self._on_update_requested)
        self._window.settings_requested.connect(self._on_settings_requested)
        self._qt_app.aboutToQuit.connect(self.stop)

    def _on_settings_requested(self) -> None:
        choice = self._provider_setup.open_dialog(
            current_provider=self._current_settings.llm_provider,
            parent=self._window,
        )
        if choice is None:
            return
        new_settings = self._provider_setup.apply_choice(self._env_settings, choice)
        self._current_settings = new_settings
        new_llm = LLMFactory(new_settings, self._strings).create()
        self._assistant_service.set_llm(new_llm)

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
