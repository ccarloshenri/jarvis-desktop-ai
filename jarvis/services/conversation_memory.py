from __future__ import annotations

from collections import deque
from typing import Deque

from jarvis.models.chat_turn import ChatTurn


class ConversationMemory:
    """Short-term rolling buffer of the last N user/assistant turns.

    Used to give the LLM enough context to resolve references like
    "ele", "isso", "aquela música" without growing tokens unbounded.
    """

    def __init__(self, max_turns: int = 10) -> None:
        if max_turns <= 0:
            raise ValueError("max_turns must be positive")
        self._buffer: Deque[ChatTurn] = deque(maxlen=max_turns)

    def add_user(self, content: str) -> None:
        self._append("user", content)

    def add_assistant(self, content: str) -> None:
        self._append("assistant", content)

    def snapshot(self) -> list[ChatTurn]:
        return list(self._buffer)

    def clear(self) -> None:
        self._buffer.clear()

    def _append(self, role: str, content: str) -> None:
        text = (content or "").strip()
        if not text:
            return
        self._buffer.append(ChatTurn(role=role, content=text))  # type: ignore[arg-type]
