from __future__ import annotations

from pathlib import Path

from jarvis.interfaces.iaudio_player import IAudioPlayer


class AudioFeedbackService:
    def __init__(self, audio_player: IAudioPlayer, startup_audio_path: Path, success_audio_path: Path) -> None:
        self._audio_player = audio_player
        self._startup_audio_path = startup_audio_path
        self._success_audio_path = success_audio_path

    def play_startup_greeting(self) -> None:
        self._audio_player.play(str(self._startup_audio_path))

    def play_success_response(self) -> None:
        self._audio_player.play(str(self._success_audio_path))
