from __future__ import annotations

from pathlib import Path

from jarvis.services.audio_feedback_service import AudioFeedbackService
from jarvis.services.startup_service import StartupService


class FakeAudioPlayer:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def play(self, file_path: str) -> None:
        self.calls.append(file_path)


def test_startup_service_plays_configured_audio() -> None:
    audio_player = FakeAudioPlayer()
    service = AudioFeedbackService(
        audio_player=audio_player,
        startup_audio_path=Path("speechs/good_morning.mp3"),
        success_audio_path=Path("speechs/understood.mp3"),
    )
    startup_service = StartupService(service)
    startup_service.execute()
    assert Path(audio_player.calls[0]).as_posix() == "speechs/good_morning.mp3"


def test_audio_feedback_service_plays_success_audio() -> None:
    audio_player = FakeAudioPlayer()
    service = AudioFeedbackService(
        audio_player=audio_player,
        startup_audio_path=Path("speechs/good_morning.mp3"),
        success_audio_path=Path("speechs/understood.mp3"),
    )
    service.play_success_response()
    assert Path(audio_player.calls[0]).as_posix() == "speechs/understood.mp3"
