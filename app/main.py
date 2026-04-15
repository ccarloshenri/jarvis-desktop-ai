from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from jarvis.config.logging_configurator import LoggingConfigurator
from jarvis.diagnostics.bundle import build_diagnostics
from jarvis.factories.application_factory import ApplicationFactory


class JarvisDesktopApplication:
    def __init__(self) -> None:
        self._logging_configurator = LoggingConfigurator()
        self._project_root = Path(__file__).resolve().parent.parent

    def run(self) -> int:
        self._logging_configurator.configure()
        diagnostics = build_diagnostics(self._project_root)
        diagnostics.logger_service.install()
        diagnostics.exception_handler.install()
        qt_app = QApplication(sys.argv)
        qt_app.setApplicationName("Jarvis")
        application = ApplicationFactory(self._project_root, diagnostics).create(qt_app)
        application.start()
        return qt_app.exec()


if __name__ == "__main__":
    raise SystemExit(JarvisDesktopApplication().run())
