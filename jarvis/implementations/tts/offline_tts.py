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
        self._engine.setProperty("rate", 165)
        self._engine.setProperty("volume", 0.95)

        def matches(voice, keywords: tuple[str, ...]) -> bool:
            identifier = f"{getattr(voice, 'name', '')} {getattr(voice, 'id', '')}".lower()
            return any(keyword in identifier for keyword in keywords)

        for tier in self._voice_priority():
            for voice in voices:
                if matches(voice, tier):
                    self._engine.setProperty("voice", voice.id)
                    return

    def _voice_priority(self) -> tuple[tuple[str, ...], ...]:
        if self._language.lower().startswith("pt"):
            return (
                ("daniel", "antonio", "ricardo", "paulo"),
                ("male",),
                ("pt-br", "pt_br", "ptb", "portuguese", "portugues", "português", "brazil", "brasil"),
            )
        return (
            ("david", "mark", "george", "james"),
            ("male",),
            ("en-us", "en_us", "english"),
        )
