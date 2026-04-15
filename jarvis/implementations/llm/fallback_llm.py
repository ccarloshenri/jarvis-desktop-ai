from __future__ import annotations

from jarvis.interfaces.illm import ILLM


class FallbackLLM(ILLM):
    def interpret(self, text: str) -> str:
        del text
        return "I do not have an AI provider configured right now, sir."
