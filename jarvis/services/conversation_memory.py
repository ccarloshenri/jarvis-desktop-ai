from __future__ import annotations

import json
import logging
from collections import deque
from pathlib import Path
from typing import Deque

from jarvis.models.chat_turn import ChatTurn

LOGGER = logging.getLogger(__name__)


class ConversationMemory:
    """Short-term rolling buffer of the last N user/assistant turns.

    Gives the LLM enough context to resolve references like "it", "that
    one", "the song" without growing tokens unbounded. Optionally
    persists to disk so the context survives a restart — boot reads
    the file, each append writes back.

    Persistence is best-effort: any I/O failure logs a warning and
    continues with the in-memory buffer. A corrupt file on disk
    degrades to an empty buffer, not a boot failure.
    """

    def __init__(
        self,
        max_turns: int = 10,
        persistence_path: Path | None = None,
    ) -> None:
        if max_turns <= 0:
            raise ValueError("max_turns must be positive")
        self._buffer: Deque[ChatTurn] = deque(maxlen=max_turns)
        self._path = persistence_path
        if persistence_path is not None:
            self._load()

    def add_user(self, content: str) -> None:
        self._append("user", content)

    def add_assistant(self, content: str) -> None:
        self._append("assistant", content)

    def snapshot(self) -> list[ChatTurn]:
        return list(self._buffer)

    def clear(self) -> None:
        self._buffer.clear()
        self._save()

    def _append(self, role: str, content: str) -> None:
        text = (content or "").strip()
        if not text:
            return
        self._buffer.append(ChatTurn(role=role, content=text))  # type: ignore[arg-type]
        self._save()

    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, ValueError) as exc:
            LOGGER.warning(
                "conversation_memory_load_failed",
                extra={"event_data": {"path": str(self._path), "error": str(exc)}},
            )
            return
        if not isinstance(data, list):
            return
        # Rebuild in order, letting the deque trim to `maxlen` as we go
        # — gracefully handles the case where someone saved a bigger
        # buffer and the app booted with a smaller max_turns.
        for item in data:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if role in ("user", "assistant") and isinstance(content, str):
                self._buffer.append(ChatTurn(role=role, content=content))  # type: ignore[arg-type]

    def _save(self) -> None:
        if self._path is None:
            return
        payload = [{"role": t.role, "content": t.content} for t in self._buffer]
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic write via temp file + rename so a crash mid-write
            # never leaves a half-flushed file for the next boot to
            # choke on.
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=0),
                encoding="utf-8",
            )
            tmp.replace(self._path)
        except OSError as exc:
            LOGGER.warning(
                "conversation_memory_save_failed",
                extra={"event_data": {"path": str(self._path), "error": str(exc)}},
            )
