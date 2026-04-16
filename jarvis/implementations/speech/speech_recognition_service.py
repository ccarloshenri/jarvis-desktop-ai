from __future__ import annotations

import logging
import time

import speech_recognition as sr

from jarvis.interfaces.ispeech_to_text import ISpeechToText

LOGGER = logging.getLogger(__name__)


_LANGUAGE_ALIASES = {
    "pt-br": "pt-BR",
    "pt_br": "pt-BR",
    "pt": "pt-BR",
    "en-us": "en-US",
    "en_us": "en-US",
    "en": "en-US",
}


class SpeechRecognitionService(ISpeechToText):
    def __init__(
        self,
        language: str = "pt-BR",
        recognizer: sr.Recognizer | None = None,
        microphone: sr.Microphone | None = None,
        listen_timeout: int = 5,
        phrase_time_limit: int = 10,
    ) -> None:
        self._language = _LANGUAGE_ALIASES.get(language.lower(), language)
        self._recognizer = recognizer or sr.Recognizer()
        self._recognizer.dynamic_energy_threshold = True
        self._recognizer.dynamic_energy_adjustment_damping = 0.15
        self._recognizer.dynamic_energy_ratio = 1.5
        self._recognizer.energy_threshold = 200
        # Phrase-end detection. 0.6s is a compromise: 0.5s cut mid-sentence
        # pauses too aggressively (users say "Jarvis... abre X" with a natural
        # gap after the wake word), 0.7s was the old default and felt sluggish.
        self._recognizer.pause_threshold = 0.6
        self._recognizer.phrase_threshold = 0.15
        self._recognizer.non_speaking_duration = 0.35
        self._microphone = microphone or sr.Microphone()
        self._listen_timeout = listen_timeout
        self._phrase_time_limit = phrase_time_limit
        self._calibrated = False

    def recalibrate(self) -> None:
        """Force a fresh ambient-noise calibration on the next listen() call.

        Used by the worker when many consecutive recognitions fail — the
        ambient level likely changed (fan/TV/speech noise) and the one-shot
        calibration from boot is stale.
        """
        self._calibrated = False

    def listen(self) -> str:
        calibrate_ms = 0
        with self._microphone as source:
            if not self._calibrated:
                t0 = time.perf_counter()
                self._recognizer.adjust_for_ambient_noise(source, duration=0.8)
                self._calibrated = True
                calibrate_ms = int((time.perf_counter() - t0) * 1000)
                LOGGER.info(
                    "stt_calibrated",
                    extra={
                        "event_data": {
                            "calibrate_ms": calibrate_ms,
                            "energy_threshold": self._recognizer.energy_threshold,
                        }
                    },
                )
            listen_start = time.perf_counter()
            audio = self._recognizer.listen(
                source,
                timeout=self._listen_timeout,
                phrase_time_limit=self._phrase_time_limit,
            )
            listen_ms = int((time.perf_counter() - listen_start) * 1000)

        recognize_start = time.perf_counter()
        try:
            transcript = self._recognizer.recognize_google(
                audio, language=self._language, show_all=False
            )
        finally:
            recognize_ms = int((time.perf_counter() - recognize_start) * 1000)
            LOGGER.info(
                "stt_breakdown",
                extra={
                    "event_data": {
                        "capture_ms": listen_ms,
                        "recognize_ms": recognize_ms,
                        "total_ms": listen_ms + recognize_ms,
                        "audio_bytes": len(audio.frame_data),
                        "language": self._language,
                    }
                },
            )
        return transcript
