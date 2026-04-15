from __future__ import annotations

from abc import ABC, abstractmethod

from jarvis.models.llm_decision import LLMDecision


class ILLM(ABC):
    @abstractmethod
    def interpret(self, text: str) -> str:
        """Interpret raw text into a natural-language response."""

    def decide(self, text: str) -> LLMDecision:
        """Return a structured decision. Default wraps interpret() as a chat reply."""
        return LLMDecision(type="chat", spoken_response=self.interpret(text).strip())

    @property
    def is_fallback(self) -> bool:
        """True if this LLM is the offline keyword-based fallback (no real reasoning)."""
        return False
