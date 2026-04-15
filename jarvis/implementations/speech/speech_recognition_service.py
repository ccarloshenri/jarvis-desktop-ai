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
        phrase_time_limit: int = 15,
    ) -> None:
        self._language = _LANGUAGE_ALIASES.get(language.lower(), language)
        self._recognizer = recognizer or sr.Recognizer()
        self._recognizer.dynamic_energy_threshold = True
        self._recognizer.dynamic_energy_adjustment_damping = 0.15
        self._recognizer.dynamic_energy_ratio = 1.5
        self._recognizer.energy_threshold = 200
        self._recognizer.pause_threshold = 0.7
        self._recognizer.phrase_threshold = 0.2
        self._recognizer.non_speaking_duration = 0.4
        self._microphone = microphone or sr.Microphone()
        self._listen_timeout = listen_timeout
        self._phrase_time_limit = phrase_time_limit
        self._calibrated = False

    def listen(self) -> str:
        calibrate_ms = 0
        with self._microphone as source:
            if not self._calibrated:
                t0 = time.perf_counter()
                self._recognizer.adjust_for_ambient_noise(source, duration=0.6)
                self._calibrated = True
                calibrate_ms = int((time.perf_counter() - t0) * 1000)
                LOGGER.debug(
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

        LOGGER.debug(
            "stt_audio_captured",
            extra={
                "event_data": {
                    "listen_ms": listen_ms,
                    "audio_bytes": len(audio.frame_data),
                    "sample_rate": audio.sample_rate,
                }
            },
        )

        recognize_start = time.perf_counter()
        try:
            transcript = self._recognizer.recognize_google(
                audio, language=self._language, show_all=False
            )
        finally:
            recognize_ms = int((time.perf_counter() - recognize_start) * 1000)
            LOGGER.debug(
                "stt_recognize_done",
                extra={
                    "event_data": {
                        "recognize_ms": recognize_ms,
                        "language": self._language,
                    }
                },
            )
        return transcript
