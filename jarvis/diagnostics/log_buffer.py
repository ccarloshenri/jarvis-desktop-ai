from __future__ import annotations

import logging
from collections import deque


class RingBufferHandler(logging.Handler):
    def __init__(self, capacity: int = 200) -> None:
        super().__init__()
        self._buffer: deque[str] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._buffer.append(self.format(record))
        except Exception:
            self.handleError(record)

    def snapshot(self, limit: int | None = None) -> list[str]:
        items = list(self._buffer)
        if limit is not None and limit >= 0:
            items = items[-limit:]
        return items


class LoggerService:
    """Attaches a ring-buffer handler to the root logger so recent log records
    can be recovered when a crash report is built."""

    def __init__(self, capacity: int = 200) -> None:
        self._handler = RingBufferHandler(capacity=capacity)
        self._installed = False

    def install(self) -> None:
        if self._installed:
            return
        root = logging.getLogger()
        for existing in root.handlers:
            if existing.formatter is not None:
                self._handler.setFormatter(existing.formatter)
                break
        root.addHandler(self._handler)
        self._installed = True

    def recent_logs(self, limit: int = 80) -> list[str]:
        return self._handler.snapshot(limit=limit)
