from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "timestamp": now.isoformat(),
            "epoch_ms": int(now.timestamp() * 1000),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "event_data"):
            payload["event_data"] = record.event_data
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_log_file_path() -> Path:
    log_dir = _project_root() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "jarvis.log"


class LoggingConfigurator:
    def configure(self) -> None:
        formatter = JsonFormatter()

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)

        file_handler = RotatingFileHandler(
            filename=str(get_log_file_path()),
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)

        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        root_logger.setLevel(logging.INFO)
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

        logging.getLogger("jarvis").setLevel(logging.INFO)

        root_logger.info(
            "logging_initialized",
            extra={"event_data": {"log_file": str(get_log_file_path())}},
        )
