from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "event_data"):
            payload["event_data"] = record.event_data
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def get_log_file_path() -> Path:
    log_dir = Path.home() / ".jarvis" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "jarvis.log"


class LoggingConfigurator:
    def configure(self) -> None:
        formatter = JsonFormatter()

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)

        file_handler = RotatingFileHandler(
            filename=str(get_log_file_path()),
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)

        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(stream_handler)
        root_logger.addHandler(file_handler)
        root_logger.info(
            "logging_initialized",
            extra={"event_data": {"log_file": str(get_log_file_path())}},
        )
