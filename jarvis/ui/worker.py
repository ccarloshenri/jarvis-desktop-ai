from __future__ import annotations

import logging
import threading
import time

from PySide6.QtCore import QObject, Qt, Signal

from jarvis.config.strings import Strings
from jarvis.interfaces.ispeech_to_text import (
    ISpeechToText,
    SpeechTimeoutError,
    UnintelligibleSpeechError,
)
from jarvis.services.assistant_service import AssistantService
from jarvis.ui.events import JarvisEventBus
from jarvis.utils.performance import Category, log, perf_log, trace_context

LOGGER = logging.getLogger(__name__)

# Small buffer after Piper stops emitting audio before we re-open the mic.
# Prevents the tail of the TTS playback (still reaching the speakers) from
# being picked up by the next listen().
_POST_SPEECH_GRACE_S = 0.25


class AssistantWorker(QObject):
    status_changed = Signal(str)
    transcript_received = Signal(str)
    response_ready = Signal(str)
    command_processed = Signal(object)
    error_occurred = Signal(str)
    finished = Signal()

    def __init__(
        self,
        strings: Strings,
        speech_to_text: ISpeechToText,
        assistant_service: AssistantService,
        event_bus: JarvisEventBus | None = None,
    ) -> None:
        super().__init__()
        self._strings = strings
        self._speech_to_text = speech_to_text
        self._assistant_service = assistant_service
        self._event_bus = event_bus
        self._running = True
        self._consecutive_stt_failures = 0
        # Gate that blocks listen() while Jarvis is speaking. The mic would
        # otherwise pick up Piper's own voice through the speakers, causing
        # a feedback loop where every subsequent recognition fails.
        self._not_speaking = threading.Event()
        self._not_speaking.set()
        if event_bus is not None:
            # DirectConnection is required: the worker runs a custom loop in
            # its QThread and never processes Qt events, so a QueuedConnection
            # would stash the False signal in a queue that nothing drains —
            # the wait() after the TTS would block forever. The slot only
            # touches `_not_speaking` (a thread-safe threading.Event), so it
            # is safe to run on whatever thread emitted the signal.
            event_bus.speaking_state_changed.connect(
                self._on_speaking_state_changed,
                Qt.ConnectionType.DirectConnection,
            )

    def _on_speaking_state_changed(self, speaking: bool) -> None:
        if speaking:
            self._not_speaking.clear()
        else:
            self._not_speaking.set()

    def run(self) -> None:
        event_bus = self._event_bus
        while self._running:
            # Block the entire listen-process cycle while Jarvis is talking.
            # Also wait a short grace period after the speaking state flips
            # off so the audio tail doesn't bleed into the next capture.
            if not self._not_speaking.is_set():
                log(Category.SYSTEM, "listen gated by speaking")
                self._not_speaking.wait()
                time.sleep(_POST_SPEECH_GRACE_S)
            # One trace per turn. Every downstream log (STT, LLM, TTS,
            # executor) inherits the trace_id via contextvars so the
            # whole interaction can be reconstructed from the log file.
            with trace_context() as trace_id:
                cycle_start = time.perf_counter()
                if event_bus is not None:
                    event_bus.emit_pipeline_state("listening")
                try:
                    log(Category.TRACE, "turn started", trace_id=trace_id)
                    self.status_changed.emit(self._strings.get("listening"))
                    listen_start = time.perf_counter()
                    transcript = self._speech_to_text.listen()
                    listen_ms = int((time.perf_counter() - listen_start) * 1000)
                    perf_log(Category.STT, "listen+transcribe", listen_ms)
                    if event_bus is not None:
                        event_bus.emit_latency("stt", listen_ms)
                    self.transcript_received.emit(transcript)
                    if event_bus is not None:
                        event_bus.emit_pipeline_state("thinking")
                    self.status_changed.emit(self._strings.get("processing"))
                    process_start = time.perf_counter()
                    result = self._assistant_service.process(transcript)
                    process_ms = int((time.perf_counter() - process_start) * 1000)
                    perf_log(Category.SYSTEM, "assistant.process", process_ms)
                    if event_bus is not None:
                        event_bus.emit_latency("llm", process_ms)
                    self.command_processed.emit(result)
                    self.response_ready.emit(result.spoken_response)
                    self.status_changed.emit(self._strings.get("ready"))
                    cycle_ms = int((time.perf_counter() - cycle_start) * 1000)
                    self._consecutive_stt_failures = 0
                    perf_log(
                        Category.PERF,
                        "turn round-trip",
                        cycle_ms,
                        listen_ms=listen_ms,
                        process_ms=process_ms,
                    )
                    if event_bus is not None:
                        event_bus.emit_latency("total", cycle_ms)
                        event_bus.emit_turn_completed(True)
                        event_bus.emit_pipeline_state("idle")
                    log(Category.TRACE, "turn done", cycle_ms=cycle_ms)
                except SpeechTimeoutError:
                    log(Category.STT, "listen timeout — no speech detected")
                    if event_bus is not None:
                        event_bus.emit_pipeline_state("idle")
                    continue
                except UnintelligibleSpeechError:
                    self._consecutive_stt_failures += 1
                    log(
                        Category.STT,
                        "unintelligible speech",
                        cycle_ms=int((time.perf_counter() - cycle_start) * 1000),
                        consecutive_failures=self._consecutive_stt_failures,
                    )
                    # Ambient noise may have shifted. Recalibrate so the next
                    # listen() starts with a fresh energy_threshold baseline.
                    if self._consecutive_stt_failures >= 3:
                        log(Category.STT, "recalibrating microphone")
                        self._speech_to_text.recalibrate()
                        self._consecutive_stt_failures = 0
                    self.error_occurred.emit(self._strings.get("could_not_catch"))
                    self.status_changed.emit(self._strings.get("ready"))
                    if event_bus is not None:
                        event_bus.emit_turn_completed(False)
                        event_bus.emit_pipeline_state("idle")
                except Exception as exc:
                    LOGGER.exception(
                        "worker unexpected error",
                        extra={"category": Category.SYSTEM, "event_data": {"message": str(exc)}},
                    )
                    self.error_occurred.emit(str(exc))
                    self.status_changed.emit(self._strings.get("ready"))
                    if event_bus is not None:
                        event_bus.emit_turn_completed(False)
                        event_bus.emit_pipeline_state("idle")
                    time.sleep(1)
        self.finished.emit()

    def stop(self) -> None:
        self._running = False
