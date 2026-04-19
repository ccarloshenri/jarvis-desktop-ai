from __future__ import annotations

from abc import ABC, abstractmethod

from jarvis.interfaces.istt_provider import CapturedAudio


class IAudioCapture(ABC):
    """Captures one utterance of microphone audio per call.

    Two implementations exist: energy-VAD `AudioCapture` (legacy / no
    deps) and `WakeWordAudioCapture` (gates on openWakeWord). Both must
    return audio of one utterance and may block indefinitely while
    waiting for it.
    """

    @abstractmethod
    def capture(self) -> CapturedAudio:
        """Block until one utterance is captured. Raise SpeechTimeoutError
        if the implementation has a per-call deadline and it elapses."""

    def recalibrate(self) -> None:
        """Re-measure ambient noise. No-op for implementations that do not
        depend on a calibrated energy threshold."""
