from __future__ import annotations

import logging
import time

import speech_recognition as sr

from jarvis.interfaces.ispeech_to_text import UnintelligibleSpeechError
from jarvis.interfaces.istt_provider import CapturedAudio, ISTTProvider

LOGGER = logging.getLogger(__name__)


_LANGUAGE_ALIASES = {
    "pt-br": "pt-BR",
    "pt_br": "pt-BR",
    "pt": "pt-BR",
    "en-us": "en-US",
    "en_us": "en-US",
    "en": "en-US",
}


class GoogleSTTProvider(ISTTProvider):
    """Transcription via Google Web Speech API (the free endpoint used
    by speech_recognition.recognize_google). Kept as a fallback for
    environments where faster-whisper can't load (e.g. model download
    blocked, broken CTranslate2 install)."""

    def __init__(self, recognizer: sr.Recognizer | None = None) -> None:
        self._recognizer = recognizer or sr.Recognizer()

    @property
    def name(self) -> str:
        return "google"

    def transcribe(self, audio: CapturedAudio, language: str) -> str:
        normalized = _LANGUAGE_ALIASES.get(language.lower(), language)
        sr_audio = sr.AudioData(
            audio.pcm_bytes,
            sample_rate=audio.sample_rate,
            sample_width=audio.sample_width,
        )
        t0 = time.perf_counter()
        try:
            text = self._recognizer.recognize_google(
                sr_audio, language=normalized, show_all=False
            )
        except sr.UnknownValueError as exc:
            raise UnintelligibleSpeechError("google could not parse audio") from exc
        finally:
            LOGGER.info(
                "google_transcribed",
                extra={
                    "event_data": {
                        "transcribe_ms": int((time.perf_counter() - t0) * 1000),
                        "language": normalized,
                        "audio_bytes": len(audio.pcm_bytes),
                    }
                },
            )
        return text
