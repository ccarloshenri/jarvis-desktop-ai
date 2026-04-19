from __future__ import annotations

import logging
import re

from jarvis.implementations.stt.wake_word_audio_capture import WakeWordAudioCapture
from jarvis.interfaces.iaudio_capture import IAudioCapture
from jarvis.interfaces.ispeech_to_text import ISpeechToText
from jarvis.interfaces.istt_provider import ISTTProvider
from jarvis.utils.performance import Category, log, timed

LOGGER = logging.getLogger(__name__)


class STTService(ISpeechToText):
    """Orchestrates microphone capture + transcription.

    Owns an AudioCapture (mic + VAD endpointing) and an ISTTProvider
    (pure audio→text). The worker only sees ISpeechToText.listen(),
    keeping it decoupled from whichever engine is active.
    """

    def __init__(
        self,
        audio_capture: IAudioCapture,
        provider: ISTTProvider,
        language: str = "pt-BR",
    ) -> None:
        self._audio_capture = audio_capture
        self._provider = provider
        self._language = language

    def listen(self) -> str:
        log(Category.VOICE, "capturing audio...")
        with timed(Category.VOICE, "audio capture"):
            audio = self._audio_capture.capture()
        log(
            Category.VOICE,
            "audio captured",
            bytes=len(audio.pcm_bytes),
            sample_rate=audio.sample_rate,
        )
        with timed(Category.STT, "transcribe", provider=self._provider.name) as m:
            text = self._provider.transcribe(audio, self._language)
            cleaned = _clean_transcript(text)
            m["chars"] = len(cleaned)
        cleaned = self._inject_wake_word_marker_if_needed(cleaned)
        log(Category.STT, f"transcribed: {cleaned!r}")
        return cleaned

    def _inject_wake_word_marker_if_needed(self, transcript: str) -> str:
        """Wake-word capture trims the wake word from the audio so Whisper
        decodes the command in PT-BR cleanly. The downstream gate in
        AssistantService still expects to see "Jarvis" in the transcript,
        so we synthesize it here when it's missing. Cheaper than plumbing
        a "wake_already_detected" flag all the way through ISpeechToText."""
        if not isinstance(self._audio_capture, WakeWordAudioCapture):
            return transcript
        if _WAKE_WORD_PRESENT_RE.search(transcript):
            return transcript
        return f"Jarvis, {transcript}".strip() if transcript else "Jarvis"

    def recalibrate(self) -> None:
        self._audio_capture.recalibrate()


_WHITESPACE_RE = re.compile(r"\s+")

# Loose match — Whisper's tail-biased decoding sometimes still emits a
# stray "Jarvis" or partial mishear ("Jarves", "Jarvez") even when we
# trim the audio. We treat any of those as "wake-word present" so we
# don't double-prefix the transcript.
_WAKE_WORD_PRESENT_RE = re.compile(
    r"\bjarv(?:is|es|iz|ez|ais|ois)\b",
    re.IGNORECASE,
)


def _clean_transcript(text: str) -> str:
    """Strip control characters, collapse whitespace, and trim.

    Whisper occasionally emits leading spaces or trailing punctuation-only
    segments; the rule-based command interpreter downstream is sensitive
    to extra whitespace, so we normalize here rather than forcing every
    caller to re-clean."""
    if not text:
        return ""
    cleaned = "".join(ch for ch in text if ch == "\n" or ch >= " ")
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned
