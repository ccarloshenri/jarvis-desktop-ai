from __future__ import annotations

from jarvis.interfaces.ispeech_events import ISpeechEvents

try:
    from PySide6.QtCore import QObject, Signal

    class JarvisEventBus(QObject, ISpeechEvents):
        speaking_started = Signal(str)
        speaking_finished = Signal(str)
        speaking_state_changed = Signal(bool)

        def __init__(self) -> None:
            super().__init__()
            self._active_speech_count = 0

        def emit_speaking_started(self, text: str) -> None:
            self._active_speech_count += 1
            self.speaking_started.emit(text)
            if self._active_speech_count == 1:
                self.speaking_state_changed.emit(True)

        def emit_speaking_finished(self, text: str) -> None:
            self._active_speech_count = max(0, self._active_speech_count - 1)
            self.speaking_finished.emit(text)
            if self._active_speech_count == 0:
                self.speaking_state_changed.emit(False)

except ModuleNotFoundError:  # pragma: no cover
    class _SimpleSignal:
        def __init__(self) -> None:
            self._callbacks: list = []

        def connect(self, callback) -> None:
            self._callbacks.append(callback)

        def emit(self, *args) -> None:
            for callback in list(self._callbacks):
                callback(*args)


    class JarvisEventBus(ISpeechEvents):
        def __init__(self) -> None:
            self.speaking_started = _SimpleSignal()
            self.speaking_finished = _SimpleSignal()
            self.speaking_state_changed = _SimpleSignal()
            self._active_speech_count = 0

        def emit_speaking_started(self, text: str) -> None:
            self._active_speech_count += 1
            self.speaking_started.emit(text)
            if self._active_speech_count == 1:
                self.speaking_state_changed.emit(True)

        def emit_speaking_finished(self, text: str) -> None:
            self._active_speech_count = max(0, self._active_speech_count - 1)
            self.speaking_finished.emit(text)
            if self._active_speech_count == 0:
                self.speaking_state_changed.emit(False)
