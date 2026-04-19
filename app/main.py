from __future__ import annotations

import sys
from pathlib import Path

# Import native-DLL-heavy optional deps BEFORE Qt.
# PySide6 ships its own copies of common runtime DLLs (OpenSSL, ICU, MSVC
# runtime). Loading Qt first can leave these deps unable to resolve their
# own DLLs on Windows:
# - faster-whisper (via ctranslate2) fails silently during WhisperModel
#   construction.
# - onnxruntime (used by Silero VAD) raises "DLL initialization routine
#   failed" when any inference session is opened.
# Forcing both to import first locks in deterministic DLL resolution.
# Guarded because each is optional.
try:  # noqa: SIM105
    import faster_whisper  # noqa: F401
except ImportError:
    pass
try:  # noqa: SIM105
    import onnxruntime  # noqa: F401
except ImportError:
    pass

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
