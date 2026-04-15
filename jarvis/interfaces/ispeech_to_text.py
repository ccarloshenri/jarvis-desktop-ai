from __future__ import annotations

from abc import ABC, abstractmethod


class ISpeechToText(ABC):
    @abstractmethod
    def listen(self) -> str:
        """Listen and return transcribed speech."""
