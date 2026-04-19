from __future__ import annotations

from abc import ABC, abstractmethod


class SpeechTimeoutError(Exception):
    """No speech detected within the listen window."""


class UnintelligibleSpeechError(Exception):
    """Audio was captured but the transcriber could not produce text."""


class ISpeechToText(ABC):
    @abstractmethod
    def listen(self) -> str:
        """Capture audio from the microphone and return the transcription.

        Raises:
            SpeechTimeoutError: no speech detected within the listen window.
            UnintelligibleSpeechError: audio captured but transcription failed.
        """

    def recalibrate(self) -> None:
        """Re-measure ambient noise. Default is a no-op for implementations
        that do not need calibration."""
