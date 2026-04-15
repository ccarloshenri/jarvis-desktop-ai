from __future__ import annotations

from jarvis.implementations.tts.offline_tts import OfflineTTS


class FakeSpeechEvents:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def emit_speaking_started(self, text: str) -> None:
        self.calls.append(("start", text))

    def emit_speaking_finished(self, text: str) -> None:
        self.calls.append(("finish", text))


class FakeVoice:
    def __init__(self) -> None:
        self.Rate = 0
        self.Volume = 0
        self.Voice = None
        self.spoken: list[str] = []

    def GetVoices(self):
        return []

    def Speak(self, text: str, flags: int) -> None:  # noqa: N802
        self.spoken.append(text)


class FakeOfflineTTS(OfflineTTS):
    def __init__(self, voice: FakeVoice, speech_events: FakeSpeechEvents) -> None:
        self._provided_voice = voice
        super().__init__(speech_events=speech_events)

    def _create_voice(self):
        return self._provided_voice


def test_tts_emits_speaking_events() -> None:
    voice = FakeVoice()
    speech_events = FakeSpeechEvents()
    tts = FakeOfflineTTS(voice=voice, speech_events=speech_events)
    tts.speak("Understood, sir.")
    assert voice.spoken == ["Understood, sir."]
    assert speech_events.calls == [("start", "Understood, sir."), ("finish", "Understood, sir.")]
