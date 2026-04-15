from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from jarvis.diagnostics.crash_context import CrashContext
from jarvis.diagnostics.crash_report import CrashReporter
from jarvis.diagnostics.exception_handler import CrashNotifier, GlobalExceptionHandler
from jarvis.diagnostics.issue_reporter import GitHubUrlIssueReporter, IGitHubIssueReporter
from jarvis.diagnostics.log_buffer import LoggerService
from jarvis.diagnostics.sanitizer import Sanitizer

DEFAULT_REPO = "carloshsousa/jarvis-desktop-ai"
DEFAULT_VERSION = "0.1.0"


@dataclass
class Diagnostics:
    logger_service: LoggerService
    crash_context: CrashContext
    crash_reporter: CrashReporter
    issue_reporter: IGitHubIssueReporter
    exception_handler: GlobalExceptionHandler
    notifier: CrashNotifier
    app_version: str
    github_repo: str


def build_diagnostics(project_root: Path) -> Diagnostics:
    app_version = os.environ.get("JARVIS_APP_VERSION", DEFAULT_VERSION).strip() or DEFAULT_VERSION
    github_repo = os.environ.get("JARVIS_GITHUB_REPO", DEFAULT_REPO).strip() or DEFAULT_REPO

    logger_service = LoggerService(capacity=300)
    crash_context = CrashContext()
    sanitizer = Sanitizer()
    crash_reporter = CrashReporter(
        logger_service=logger_service,
        crash_context=crash_context,
        sanitizer=sanitizer,
        app_version=app_version,
        crash_dir=project_root / "logs" / "crashes",
    )
    issue_reporter = GitHubUrlIssueReporter(repo=github_repo, crash_reporter=crash_reporter)
    notifier = CrashNotifier()
    exception_handler = GlobalExceptionHandler(
        crash_reporter=crash_reporter,
        issue_reporter=issue_reporter,
        notifier=notifier,
    )
    return Diagnostics(
        logger_service=logger_service,
        crash_context=crash_context,
        crash_reporter=crash_reporter,
        issue_reporter=issue_reporter,
        exception_handler=exception_handler,
        notifier=notifier,
        app_version=app_version,
        github_repo=github_repo,
    )
