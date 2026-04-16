from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from jarvis.models.chat_turn import ChatTurn
from jarvis.models.llm_decision import LLMDecision


class ILLM(ABC):
    @abstractmethod
    def interpret(self, text: str) -> str:
        """Interpret raw text into a natural-language response."""

    def decide(self, text: str, history: Sequence[ChatTurn] | None = None) -> LLMDecision:
        """Return a structured decision. Default wraps interpret() as a chat reply.

        Implementations that support multi-turn context should consume `history`
        (oldest first); stateless implementations are free to ignore it.
        """
        return LLMDecision(type="chat", spoken_response=self.interpret(text).strip())

    @property
    def is_fallback(self) -> bool:
        """True if this LLM is the offline keyword-based fallback (no real reasoning)."""
        return False
