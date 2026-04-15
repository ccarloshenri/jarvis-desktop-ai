from __future__ import annotations

from jarvis.interfaces.ispeech_events import ISpeechEvents
from jarvis.interfaces.itext_to_speech import ITextToSpeech


class OfflineTTS(ITextToSpeech):
    def __init__(self, speech_events: ISpeechEvents | None = None) -> None:
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
        self._engine.setProperty("rate", 162)
        self._engine.setProperty("volume", 0.9)
        for voice in voices:
            name = getattr(voice, "name", "").lower()
            if "zira" in name or "david" in name or "english" in name:
                self._engine.setProperty("voice", voice.id)
                break
