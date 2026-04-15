from __future__ import annotations

from abc import ABC, abstractmethod


class IAudioPlayer(ABC):
    @abstractmethod
    def play(self, file_path: str) -> None:
        """Play a prerecorded audio file."""
