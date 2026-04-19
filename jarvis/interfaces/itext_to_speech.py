from __future__ import annotations

from abc import ABC, abstractmethod


class ITextToSpeech(ABC):
    @abstractmethod
    def speak(self, text: str) -> None:
        """Speak text to the user."""

    def speak_stream_chunk(self, text: str) -> None:
        """Append a chunk to the in-progress streaming utterance.

        Default implementation buffers chunks in memory and speaks them
        all at once on `speak_stream_end`. Real streaming TTS engines
        (VoiceService/Piper, Kokoro, ElevenLabs) override to start
        synthesis as soon as a chunk arrives.
        """
        if not hasattr(self, "_tts_stream_buffer"):
            self._tts_stream_buffer: list[str] = []
        if text and text.strip():
            self._tts_stream_buffer.append(text.strip())

    def speak_stream_end(self) -> None:
        """Close the streaming utterance and emit the buffered audio.

        Safe to call without matching `speak_stream_chunk` calls (no-op).
        """
        buffer = getattr(self, "_tts_stream_buffer", None)
        if buffer:
            self.speak(" ".join(buffer))
            buffer.clear()
