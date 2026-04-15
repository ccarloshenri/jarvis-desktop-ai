from __future__ import annotations

import platform
import sys
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType

from jarvis.diagnostics.crash_context import CrashContext
from jarvis.diagnostics.log_buffer import LoggerService
from jarvis.diagnostics.sanitizer import Sanitizer


@dataclass
class CrashReport:
    id: str
    timestamp: str
    app_version: str
    operating_system: str
    python_version: str
    provider: str
    current_action: str
    error_type: str
    error_message: str
    stack_trace: str
    recent_logs: list[str] = field(default_factory=list)
    extra: dict[str, str] = field(default_factory=dict)


class CrashReporter:
    def __init__(
        self,
        logger_service: LoggerService,
        crash_context: CrashContext,
        sanitizer: Sanitizer,
        app_version: str,
        crash_dir: Path,
        log_limit: int = 80,
    ) -> None:
        self._logger_service = logger_service
        self._crash_context = crash_context
        self._sanitizer = sanitizer
        self._app_version = app_version
        self._crash_dir = crash_dir
        self._log_limit = log_limit
        self._crash_dir.mkdir(parents=True, exist_ok=True)

    def build_report(
        self,
        exc_type: type[BaseException],
        exc: BaseException,
        tb: TracebackType | None,
    ) -> CrashReport:
        stack = "".join(traceback.format_exception(exc_type, exc, tb))
        ctx = self._crash_context.snapshot()
        logs = self._logger_service.recent_logs(limit=self._log_limit)
        return CrashReport(
            id=uuid.uuid4().hex[:12],
            timestamp=datetime.now(timezone.utc).isoformat(),
            app_version=self._app_version,
            operating_system=f"{platform.system()} {platform.release()}",
            python_version=sys.version.split()[0],
            provider=ctx.provider,
            current_action=self._sanitizer.sanitize(ctx.current_action),
            error_type=exc_type.__name__,
            error_message=self._sanitizer.sanitize(str(exc)),
            stack_trace=self._sanitizer.sanitize(stack),
            recent_logs=self._sanitizer.sanitize_lines(logs),
            extra={k: self._sanitizer.sanitize(v) for k, v in ctx.extra.items()},
        )

    def persist(self, report: CrashReport) -> Path:
        safe_ts = report.timestamp.replace(":", "-")
        path = self._crash_dir / f"crash_{safe_ts}_{report.id}.md"
        path.write_text(self.render_markdown(report), encoding="utf-8")
        return path

    def render_markdown(self, report: CrashReport) -> str:
        logs_block = "\n".join(report.recent_logs) if report.recent_logs else "(no logs captured)"
        extra_block = (
            "\n".join(f"- **{k}**: {v}" for k, v in report.extra.items())
            if report.extra
            else "- (none)"
        )
        return (
            f"## Summary\n"
            f"`{report.error_type}`: {report.error_message}\n\n"
            f"## Environment\n"
            f"- **App version**: {report.app_version}\n"
            f"- **OS**: {report.operating_system}\n"
            f"- **Python**: {report.python_version}\n"
            f"- **Provider**: {report.provider}\n"
            f"- **Timestamp (UTC)**: {report.timestamp}\n"
            f"- **Report id**: {report.id}\n\n"
            f"## Action in progress\n"
            f"{report.current_action or '(none)'}\n\n"
            f"## Error\n"
            f"`{report.error_type}`: {report.error_message}\n\n"
            f"## Stack trace\n"
            f"```\n{report.stack_trace}\n```\n\n"
            f"## Recent logs\n"
            f"```\n{logs_block}\n```\n\n"
            f"## Extra context\n"
            f"{extra_block}\n"
        )
