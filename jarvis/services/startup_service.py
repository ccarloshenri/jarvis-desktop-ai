from __future__ import annotations

from jarvis.config.strings import Strings
from jarvis.interfaces.itext_to_speech import ITextToSpeech


class StartupService:
    def __init__(self, strings: Strings, text_to_speech: ITextToSpeech) -> None:
        self._strings = strings
        self._text_to_speech = text_to_speech

    def execute(self) -> None:
        self._text_to_speech.speak(self._strings.get("system_online"))
