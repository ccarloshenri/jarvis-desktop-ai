from __future__ import annotations

from jarvis.implementations.tts.offline_tts import OfflineTTS


class FakeSpeechEvents:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def emit_speaking_started(self, text: str) -> None:
        self.calls.append(("start", text))

    def emit_speaking_finished(self, text: str) -> None:
        self.calls.append(("finish", text))


class FakeEngine:
    def __init__(self) -> None:
        self.properties = {}
        self.spoken: list[str] = []

    def getProperty(self, name: str):
        if name == "voices":
            return []
        return self.properties.get(name)

    def setProperty(self, name: str, value) -> None:
        self.properties[name] = value

    def say(self, text: str) -> None:
        self.spoken.append(text)

    def runAndWait(self) -> None:
        return None


class FakeOfflineTTS(OfflineTTS):
    def __init__(self, engine: FakeEngine, speech_events: FakeSpeechEvents) -> None:
        self._provided_engine = engine
        super().__init__(speech_events=speech_events)

    def _create_engine(self):
        return self._provided_engine


def test_tts_emits_speaking_events() -> None:
    engine = FakeEngine()
    speech_events = FakeSpeechEvents()
    tts = FakeOfflineTTS(engine=engine, speech_events=speech_events)
    tts.speak("Understood, sir.")
    assert engine.spoken == ["Understood, sir."]
    assert speech_events.calls == [("start", "Understood, sir."), ("finish", "Understood, sir.")]
