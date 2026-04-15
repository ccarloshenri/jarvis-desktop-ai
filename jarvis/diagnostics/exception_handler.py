from __future__ import annotations

import logging
import sys
import threading
from types import TracebackType

from PySide6.QtCore import QObject, Signal

from jarvis.diagnostics.crash_report import CrashReport, CrashReporter
from jarvis.diagnostics.issue_reporter import IGitHubIssueReporter

LOGGER = logging.getLogger(__name__)


class CrashNotifier(QObject):
    """Qt signal hub — lets background-thread crashes reach the UI thread
    through a queued signal/slot connection."""

    crash_occurred = Signal(object)


class GlobalExceptionHandler:
    def __init__(
        self,
        crash_reporter: CrashReporter,
        issue_reporter: IGitHubIssueReporter,
        notifier: CrashNotifier,
    ) -> None:
        self._crash_reporter = crash_reporter
        self._issue_reporter = issue_reporter
        self._notifier = notifier
        self._previous_excepthook = None
        self._previous_thread_hook = None

    @property
    def notifier(self) -> CrashNotifier:
        return self._notifier

    @property
    def issue_reporter(self) -> IGitHubIssueReporter:
        return self._issue_reporter

    def install(self) -> None:
        self._previous_excepthook = sys.excepthook
        sys.excepthook = self._handle_exception
        self._previous_thread_hook = threading.excepthook
        threading.excepthook = self._handle_thread_exception

    def handle(
        self,
        exc_type: type[BaseException],
        exc: BaseException,
        tb: TracebackType | None,
    ) -> CrashReport:
        report = self._crash_reporter.build_report(exc_type, exc, tb)
        try:
            path = self._crash_reporter.persist(report)
            LOGGER.error(
                "crash_captured",
                extra={"event_data": {"crash_id": report.id, "file": str(path)}},
            )
        except Exception:
            LOGGER.exception("crash_persist_failed")
        self._notifier.crash_occurred.emit(report)
        return report

    def _handle_exception(self, exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            if self._previous_excepthook is not None:
                self._previous_excepthook(exc_type, exc, tb)
            return
        try:
            self.handle(exc_type, exc, tb)
        except Exception:
            LOGGER.exception("crash_handler_failed")
        if self._previous_excepthook is not None:
            self._previous_excepthook(exc_type, exc, tb)

    def _handle_thread_exception(self, args) -> None:
        try:
            self.handle(args.exc_type, args.exc_value, args.exc_traceback)
        except Exception:
            LOGGER.exception("crash_handler_failed")
        if self._previous_thread_hook is not None:
            self._previous_thread_hook(args)
