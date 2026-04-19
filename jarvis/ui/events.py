from __future__ import annotations

from jarvis.interfaces.ispeech_events import ISpeechEvents

try:
    from PySide6.QtCore import QObject, Signal

    class JarvisEventBus(QObject, ISpeechEvents):
        speaking_started = Signal(str)
        speaking_finished = Signal(str)
        speaking_state_changed = Signal(bool)
        # Live audio level from the mic capture (0-1 normalized). Emitted
        # at ~12Hz while waiting for wake or recording a command, so the
        # HUD can animate a VU meter without the UI doing its own audio
        # work. Idle periods emit 0.0 periodically so the bar decays.
        mic_level_changed = Signal(float)
        # Pipeline state for the HUD's status strip. Values: "idle",
        # "listening", "processing", "thinking", "speaking". Distinct from
        # speaking_state_changed (kept for back-compat with the worker's
        # listen gate).
        pipeline_state_changed = Signal(str)
        # Per-turn telemetry. latency_recorded emits (component, ms)
        # pairs — "stt", "llm", "tts", "total" — so the stats panel can
        # render rolling averages without scraping the log file.
        latency_recorded = Signal(str, int)
        turn_completed = Signal(bool)
        wake_fired = Signal()

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

        def emit_mic_level(self, level: float) -> None:
            self.mic_level_changed.emit(float(level))

        def emit_pipeline_state(self, state: str) -> None:
            self.pipeline_state_changed.emit(state)

        def emit_latency(self, component: str, ms: int) -> None:
            self.latency_recorded.emit(component, int(ms))

        def emit_turn_completed(self, success: bool) -> None:
            self.turn_completed.emit(bool(success))

        def emit_wake_fired(self) -> None:
            self.wake_fired.emit()

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
            self.mic_level_changed = _SimpleSignal()
            self.pipeline_state_changed = _SimpleSignal()
            self.latency_recorded = _SimpleSignal()
            self.turn_completed = _SimpleSignal()
            self.wake_fired = _SimpleSignal()
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

        def emit_mic_level(self, level: float) -> None:
            self.mic_level_changed.emit(float(level))

        def emit_pipeline_state(self, state: str) -> None:
            self.pipeline_state_changed.emit(state)

        def emit_latency(self, component: str, ms: int) -> None:
            self.latency_recorded.emit(component, int(ms))

        def emit_turn_completed(self, success: bool) -> None:
            self.turn_completed.emit(bool(success))

        def emit_wake_fired(self) -> None:
            self.wake_fired.emit()
