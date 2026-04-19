from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CapturedAudio:
    """Raw PCM captured from the microphone, ready for transcription."""

    pcm_bytes: bytes
    sample_rate: int
    sample_width: int  # bytes per sample (2 = 16-bit)
    channels: int = 1


class ISTTProvider(ABC):
    @abstractmethod
    def transcribe(self, audio: CapturedAudio, language: str) -> str:
        """Return the transcribed text. Raise UnintelligibleSpeechError on
        empty/unrecognizable output."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for logging (e.g. 'whisper', 'google')."""
