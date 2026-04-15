from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, Signal

from jarvis.services.update_checker import ReleaseInfo, UpdateChecker
from jarvis.services.updater import Updater, UpdateError

LOGGER = logging.getLogger(__name__)


class UpdateService(QObject):
    """Qt-aware orchestrator: runs the HTTP check on a background thread and
    emits a signal when a newer release is found. The UI thread decides what
    to do with it (show a banner, start the download, etc.)."""

    update_available = Signal(object)
    update_failed = Signal(str)

    def __init__(self, checker: UpdateChecker, updater: Updater) -> None:
        super().__init__()
        self._checker = checker
        self._updater = updater

    def check_async(self) -> None:
        threading.Thread(target=self._run_check, name="jarvis-update-check", daemon=True).start()

    def apply_async(self, release: ReleaseInfo) -> None:
        threading.Thread(
            target=self._run_apply,
            args=(release,),
            name="jarvis-update-apply",
            daemon=True,
        ).start()

    def _run_check(self) -> None:
        try:
            release = self._checker.check()
        except Exception as exc:
            LOGGER.exception("update_check_unexpected_error")
            self.update_failed.emit(str(exc))
            return
        if release is not None:
            self.update_available.emit(release)

    def _run_apply(self, release: ReleaseInfo) -> None:
        try:
            self._updater.apply(release)
        except UpdateError as exc:
            LOGGER.error("update_apply_failed", extra={"event_data": {"error": str(exc)}})
            self.update_failed.emit(str(exc))
        except Exception as exc:
            LOGGER.exception("update_apply_unexpected_error")
            self.update_failed.emit(str(exc))
