from __future__ import annotations

from jarvis.services.audio_feedback_service import AudioFeedbackService


class StartupService:
    def __init__(self, audio_feedback: AudioFeedbackService) -> None:
        self._audio_feedback = audio_feedback

    def execute(self) -> None:
        self._audio_feedback.play_startup_greeting()
