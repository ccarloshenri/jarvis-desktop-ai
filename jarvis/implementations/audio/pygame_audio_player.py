from __future__ import annotations

import threading
import time
from pathlib import Path

from jarvis.interfaces.iaudio_player import IAudioPlayer
from jarvis.interfaces.ispeech_events import ISpeechEvents


class PygameAudioPlayer(IAudioPlayer):
    def __init__(self, speech_events: ISpeechEvents | None = None) -> None:
        self._speech_events = speech_events
        self._lock = threading.Lock()
        self._mixer = self._build_mixer()
        self._initialize_mixer()

    def play(self, file_path: str) -> None:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        playback_thread = threading.Thread(
            target=self._playback_worker,
            args=(path,),
            daemon=True,
            name="jarvis-audio-player",
        )
        playback_thread.start()

    def _build_mixer(self):
        import pygame

        return pygame.mixer

    def _initialize_mixer(self) -> None:
        if not self._mixer.get_init():
            self._mixer.init()

    def _playback_worker(self, path: Path) -> None:
        with self._lock:
            if self._speech_events is not None:
                self._speech_events.emit_speaking_started(path.name)
            try:
                self._mixer.music.stop()
                self._mixer.music.load(str(path))
                self._mixer.music.play()
                while self._mixer.music.get_busy():
                    time.sleep(0.05)
            finally:
                self._mixer.music.stop()
                if self._speech_events is not None:
                    self._speech_events.emit_speaking_finished(path.name)
