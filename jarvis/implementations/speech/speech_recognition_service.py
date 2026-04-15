from __future__ import annotations

import speech_recognition as sr

from jarvis.interfaces.ispeech_to_text import ISpeechToText


class SpeechRecognitionService(ISpeechToText):
    def __init__(
        self,
        recognizer: sr.Recognizer | None = None,
        microphone: sr.Microphone | None = None,
        listen_timeout: int = 1,
        phrase_time_limit: int = 6,
    ) -> None:
        self._recognizer = recognizer or sr.Recognizer()
        self._microphone = microphone or sr.Microphone()
        self._listen_timeout = listen_timeout
        self._phrase_time_limit = phrase_time_limit

    def listen(self) -> str:
        with self._microphone as source:
            self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = self._recognizer.listen(
                source,
                timeout=self._listen_timeout,
                phrase_time_limit=self._phrase_time_limit,
            )
        return self._recognizer.recognize_google(audio)
