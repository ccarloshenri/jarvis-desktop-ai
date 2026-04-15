from __future__ import annotations

from abc import ABC, abstractmethod


class ITextToSpeech(ABC):
    @abstractmethod
    def speak(self, text: str) -> None:
        """Speak text to the user."""
