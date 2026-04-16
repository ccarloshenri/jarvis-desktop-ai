from __future__ import annotations

from abc import ABC, abstractmethod


class ISpeechToText(ABC):
    @abstractmethod
    def listen(self) -> str:
        """Listen and return transcribed speech."""

    def recalibrate(self) -> None:
        """Re-measure ambient noise. Default is a no-op for implementations
        that do not need calibration."""
