from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from jarvis.models.chat_turn import ChatTurn
from jarvis.models.llm_decision import LLMDecision


class ILLM(ABC):
    @abstractmethod
    def decide(self, text: str, history: Sequence[ChatTurn] | None = None) -> LLMDecision:
        """Return a structured decision from the user's utterance.

        Implementations are free to ignore `history` but should consume
        it when multi-turn context improves disambiguation.
        """

    def interpret(self, text: str) -> str:
        """Convenience: return just the spoken response text."""
        return self.decide(text).spoken_response
