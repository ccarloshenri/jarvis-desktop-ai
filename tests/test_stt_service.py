from __future__ import annotations

import pytest

from jarvis.implementations.stt.stt_service import STTService, _clean_transcript
from jarvis.interfaces.ispeech_to_text import (
    SpeechTimeoutError,
    UnintelligibleSpeechError,
)
from jarvis.interfaces.istt_provider import CapturedAudio, ISTTProvider


class FakeAudioCapture:
    def __init__(self, audio: CapturedAudio | None = None, raise_timeout: bool = False) -> None:
        self._audio = audio or CapturedAudio(
            pcm_bytes=b"\x00" * 16000, sample_rate=16000, sample_width=2
        )
        self._raise_timeout = raise_timeout
        self.recalibrate_calls = 0

    def capture(self) -> CapturedAudio:
        if self._raise_timeout:
            raise SpeechTimeoutError("no speech")
        return self._audio

    def recalibrate(self) -> None:
        self.recalibrate_calls += 1


class FakeProvider(ISTTProvider):
    def __init__(self, output: str = "abre o spotify", raise_unintelligible: bool = False) -> None:
        self._output = output
        self._raise = raise_unintelligible
        self.last_language: str | None = None

    @property
    def name(self) -> str:
        return "fake"

    def transcribe(self, audio: CapturedAudio, language: str) -> str:
        self.last_language = language
        if self._raise:
            raise UnintelligibleSpeechError("fake failed")
        return self._output


def test_listen_returns_cleaned_transcript_from_provider() -> None:
    service = STTService(
        audio_capture=FakeAudioCapture(),
        provider=FakeProvider(output="  abre   o spotify  "),
        language="pt-BR",
    )
    assert service.listen() == "abre o spotify"


def test_listen_passes_language_to_provider() -> None:
    provider = FakeProvider()
    service = STTService(audio_capture=FakeAudioCapture(), provider=provider, language="pt-BR")
    service.listen()
    assert provider.last_language == "pt-BR"


def test_listen_propagates_timeout_from_capture() -> None:
    service = STTService(
        audio_capture=FakeAudioCapture(raise_timeout=True),
        provider=FakeProvider(),
        language="pt-BR",
    )
    with pytest.raises(SpeechTimeoutError):
        service.listen()


def test_listen_propagates_unintelligible_from_provider() -> None:
    service = STTService(
        audio_capture=FakeAudioCapture(),
        provider=FakeProvider(raise_unintelligible=True),
        language="pt-BR",
    )
    with pytest.raises(UnintelligibleSpeechError):
        service.listen()


def test_recalibrate_forwards_to_capture() -> None:
    capture = FakeAudioCapture()
    service = STTService(audio_capture=capture, provider=FakeProvider(), language="pt-BR")
    service.recalibrate()
    assert capture.recalibrate_calls == 1


def test_clean_transcript_strips_control_chars_and_collapses_whitespace() -> None:
    assert _clean_transcript("  foo\x00  bar\nbaz  ") == "foo bar baz"
    assert _clean_transcript("") == ""
