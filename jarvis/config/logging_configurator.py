"""Logging configuration: human-readable stream + JSON rotating file.

Two handlers on the root logger:

- **Stream (terminal)**: short, scannable text. Format follows the
  convention requested for perf debugging:
      HH:MM:SS.mmm [TRACE abc12345] [CATEGORY] message (k=v k=v)
  The [TRACE ...] and [CATEGORY] brackets are omitted when the record
  has no trace_id / category, so unrelated boot-time logs stay clean.

- **File (jarvis.log)**: full JSON with timestamp, epoch_ms, trace_id,
  category, and event_data. Machine-readable for post-mortem analysis.

A single Filter injects trace_id + category from contextvars onto every
record so callers don't have to pass them explicitly — set the trace
context once around a turn and every downstream log inherits it.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from jarvis.utils.performance import current_category, current_trace_id


class ContextFilter(logging.Filter):
    """Stamp trace_id and category onto every record from the contextvars.

    `extra={"category": "..."}` on a specific log call still wins — we only
    fall back to the context var when the record didn't set its own.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "trace_id"):
            record.trace_id = current_trace_id() or ""  # type: ignore[attr-defined]
        if not hasattr(record, "category"):
            record.category = current_category() or ""  # type: ignore[attr-defined]
        if not hasattr(record, "event_data"):
            record.event_data = {}  # type: ignore[attr-defined]
        if not hasattr(record, "perf"):
            record.perf = False  # type: ignore[attr-defined]
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "timestamp": now.isoformat(),
            "epoch_ms": int(now.timestamp() * 1000),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", "") or None,
            "category": getattr(record, "category", "") or None,
            "perf": bool(getattr(record, "perf", False)),
            "event_data": getattr(record, "event_data", {}) or {},
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # ensure_ascii=False keeps pt-BR readable in the log file.
        return json.dumps(payload, ensure_ascii=False)


class HumanFormatter(logging.Formatter):
    """Concise terminal formatter. Looks like:

        14:03:22.481 [TRACE 1a2b3c4d] [PERF] [STT] transcribe (duration_ms=812)
        14:03:22.482 [TRACE 1a2b3c4d] [STT] transcribed: 'abre o spotify'

    Bracketed tags are omitted when empty so boot-time system logs don't
    look like they have blank placeholders.
    """

    def format(self, record: logging.LogRecord) -> str:
        now = datetime.now()
        ts = now.strftime("%H:%M:%S") + f".{now.microsecond // 1000:03d}"

        parts: list[str] = [ts]
        trace_id = getattr(record, "trace_id", "") or ""
        if trace_id:
            parts.append(f"[TRACE {trace_id}]")
        is_perf = bool(getattr(record, "perf", False))
        category = getattr(record, "category", "") or ""
        if is_perf:
            parts.append("[PERF]")
        # Avoid rendering "[PERF] [PERF]" when the log was tagged with
        # Category.PERF *and* the perf flag — which is the common case
        # for standalone perf_log() calls that don't belong to another
        # subsystem (e.g., the turn round-trip summary).
        if category and not (is_perf and category == "PERF"):
            parts.append(f"[{category}]")

        message = record.getMessage()
        event_data = getattr(record, "event_data", {}) or {}
        if event_data:
            rendered = " ".join(
                f"{k}={_short_repr(v)}" for k, v in event_data.items()
            )
            message = f"{message} ({rendered})"

        line = " ".join(parts + [message])
        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        return line


def _short_repr(value: object, limit: int = 120) -> str:
    """Render a log field compactly: strings get quoted, long values
    truncated. Keeps the terminal scannable when a field happens to carry
    the whole LLM response or a long transcript."""
    if isinstance(value, str):
        if len(value) > limit:
            return repr(value[: limit - 1] + "…")
        return repr(value)
    rendered = repr(value)
    if len(rendered) > limit:
        return rendered[: limit - 1] + "…"
    return rendered


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_log_file_path() -> Path:
    log_dir = _project_root() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "jarvis.log"


class LoggingConfigurator:
    def configure(self) -> None:
        context_filter = ContextFilter()

        # Force UTF-8 on the terminal stream. Windows Python 3 defaults
        # stdout/stderr to the console's ANSI codepage (cp1252 in pt-BR),
        # which rejects Unicode accents and falls back to '?' replacement
        # or mojibake. Reconfiguring stderr here fixes log lines like
        # "Você" / "Hoje é" in the live terminal without breaking tests.
        if hasattr(sys.stderr, "reconfigure"):
            try:
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                # Non-Windows or already configured — nothing to do.
                pass
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(HumanFormatter())
        stream_handler.addFilter(context_filter)

        file_handler = RotatingFileHandler(
            filename=str(get_log_file_path()),
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(JsonFormatter())
        file_handler.addFilter(context_filter)

        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        root_logger.setLevel(self._resolve_level())
        root_logger.addHandler(stream_handler)
        root_logger.addHandler(file_handler)

        for noisy in (
            "comtypes",
            "comtypes._comobject",
            "comtypes._vtbl",
            "comtypes.client",
            "comtypes.client._events",
            "PIL",
            "urllib3",
            "asyncio",
        ):
            logging.getLogger(noisy).setLevel(logging.WARNING)

        logging.getLogger("jarvis").setLevel(self._resolve_level())

        root_logger.info(
            "logging_initialized",
            extra={
                "category": "SYSTEM",
                "event_data": {"log_file": str(get_log_file_path())},
            },
        )

    def _resolve_level(self) -> int:
        # JARVIS_VERBOSE flips the whole root to DEBUG. JARVIS_DEBUG
        # (historical) controls the in-app debug panel but is treated the
        # same here so the existing env var keeps working.
        flag = (os.getenv("JARVIS_VERBOSE") or os.getenv("JARVIS_DEBUG") or "").strip().lower()
        if flag in {"1", "true", "yes", "on", "debug", "verbose"}:
            return logging.DEBUG
        return logging.INFO
