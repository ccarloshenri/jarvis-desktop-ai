from __future__ import annotations

from jarvis.interfaces.ispeech_events import ISpeechEvents
from jarvis.interfaces.itext_to_speech import ITextToSpeech


class OfflineTTS(ITextToSpeech):
    def __init__(
        self,
        speech_events: ISpeechEvents | None = None,
        language: str = "pt-BR",
    ) -> None:
        self._language = language
        self._engine = self._create_engine()
        self._speech_events = speech_events
        self._configure_voice()

    def speak(self, text: str) -> None:
        if self._speech_events is not None:
            self._speech_events.emit_speaking_started(text)
        try:
            self._engine.say(text)
            self._engine.runAndWait()
        finally:
            if self._speech_events is not None:
                self._speech_events.emit_speaking_finished(text)

    def _create_engine(self):
        import pyttsx3

        return pyttsx3.init()

    def _configure_voice(self) -> None:
        voices = self._engine.getProperty("voices")
        self._engine.setProperty("rate", 168)
        self._engine.setProperty("volume", 0.95)
        preferred = self._voice_keywords()
        for voice in voices:
            identifier = f"{getattr(voice, 'name', '')} {getattr(voice, 'id', '')}".lower()
            if any(keyword in identifier for keyword in preferred):
                self._engine.setProperty("voice", voice.id)
                return

    def _voice_keywords(self) -> tuple[str, ...]:
        if self._language.lower().startswith("pt"):
            return ("portuguese", "portugues", "português", "maria", "daniel", "helena", "brazil", "brasil", "pt-br", "pt_br", "ptb")
        return ("english", "zira", "david", "en-us", "en_us")
