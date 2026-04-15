from __future__ import annotations

import re

from jarvis.config.strings import Strings
from jarvis.interfaces.illm import ILLM


class FallbackLLM(ILLM):
    """Intelligent offline fallback.

    Matches the user's utterance against keyword intents and responds
    in the configured language. Used when no cloud LLM provider is set.
    """

    def __init__(self, strings: Strings | None = None) -> None:
        self._strings = strings or Strings()

    @property
    def is_fallback(self) -> bool:
        return True

    def interpret(self, text: str) -> str:
        normalized = self._normalize(text)
        if not normalized:
            return self._strings.get("empty_transcript")

        if self._matches(normalized, (
            "ola", "oi", "bom dia", "boa tarde", "boa noite",
            "hello", "hi", "good morning", "good afternoon", "good evening",
        )):
            return self._strings.get("greeting")

        if self._matches(normalized, (
            "tudo bem", "como voce esta", "como vai", "how are you",
        )):
            return self._strings.get("how_are_you")

        if self._matches(normalized, (
            "quem e voce", "qual seu nome", "quem es tu", "who are you", "what is your name",
        )):
            return self._strings.get("who_are_you")

        if self._matches(normalized, (
            "obrigado", "obrigada", "valeu", "thanks", "thank you",
        )):
            return self._strings.get("thanks")

        if self._matches(normalized, (
            "tchau", "ate logo", "adeus", "bye", "goodbye", "see you",
        )):
            return self._strings.get("goodbye")

        if self._matches(normalized, (
            "ajuda", "o que voce faz", "o que pode fazer", "help", "what can you do",
        )):
            return self._strings.get("help")

        if self._matches(normalized, (
            "piada", "conte uma piada", "joke", "tell me a joke",
        )):
            return self._strings.get("joke")

        return self._strings.get("fallback_unknown")

    def _normalize(self, text: str) -> str:
        lowered = text.lower()
        replacements = str.maketrans("áàâãäéèêëíìîïóòôõöúùûüç", "aaaaaeeeeiiiiooooouuuuc")
        lowered = lowered.translate(replacements)
        return " ".join(re.sub(r"[^\w\s]", " ", lowered).split())

    def _matches(self, text: str, phrases: tuple[str, ...]) -> bool:
        return any(phrase in text for phrase in phrases)
