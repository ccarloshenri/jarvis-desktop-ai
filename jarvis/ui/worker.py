from __future__ import annotations

import logging
import threading
import time

import speech_recognition as sr
from PySide6.QtCore import QObject, Signal

from jarvis.config.strings import Strings
from jarvis.interfaces.ispeech_to_text import ISpeechToText
from jarvis.services.assistant_service import AssistantService
from jarvis.ui.events import JarvisEventBus

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
        self._running = True
        self._consecutive_stt_failures = 0
        # Gate that blocks listen() while Jarvis is speaking. The mic would
        # otherwise pick up Piper's own voice through the speakers, causing
        # a feedback loop where every subsequent recognition fails.
        self._not_speaking = threading.Event()
        self._not_speaking.set()
        if event_bus is not None:
            event_bus.speaking_state_changed.connect(self._on_speaking_state_changed)

    def _on_speaking_state_changed(self, speaking: bool) -> None:
        if speaking:
            self._not_speaking.clear()
        else:
            self._not_speaking.set()

    def run(self) -> None:
        while self._running:
            # Block the entire listen-process cycle while Jarvis is talking.
            # Also wait a short grace period after the speaking state flips
            # off so the audio tail doesn't bleed into the next capture.
            if not self._not_speaking.is_set():
                LOGGER.info("listen_gated_by_speaking")
                self._not_speaking.wait()
                time.sleep(_POST_SPEECH_GRACE_S)
            cycle_start = time.perf_counter()
            try:
                self.status_changed.emit(self._strings.get("listening"))
                listen_start = time.perf_counter()
                transcript = self._speech_to_text.listen()
                listen_ms = int((time.perf_counter() - listen_start) * 1000)
                self.transcript_received.emit(transcript)
                self.status_changed.emit(self._strings.get("processing"))
                process_start = time.perf_counter()
                result = self._assistant_service.process(transcript)
                process_ms = int((time.perf_counter() - process_start) * 1000)
                self.command_processed.emit(result)
                self.response_ready.emit(result.spoken_response)
                self.status_changed.emit(self._strings.get("ready"))
                cycle_ms = int((time.perf_counter() - cycle_start) * 1000)
                self._consecutive_stt_failures = 0
                LOGGER.info(
                    "cycle_done",
                    extra={
                        "event_data": {
                            "transcript": transcript,
                            "listen_ms": listen_ms,
                            "process_ms": process_ms,
                            "cycle_ms": cycle_ms,
                        }
                    },
                )
            except sr.WaitTimeoutError:
                LOGGER.info("stt_wait_timeout")
                continue
            except sr.UnknownValueError:
                self._consecutive_stt_failures += 1
                LOGGER.info(
                    "stt_unknown_value",
                    extra={
                        "event_data": {
                            "cycle_ms": int((time.perf_counter() - cycle_start) * 1000),
                            "consecutive_failures": self._consecutive_stt_failures,
                        }
                    },
                )
                # Ambient noise may have shifted. Recalibrate so the next
                # listen() starts with a fresh energy_threshold baseline.
                if self._consecutive_stt_failures >= 3:
                    LOGGER.info("stt_recalibrate_triggered")
                    self._speech_to_text.recalibrate()
                    self._consecutive_stt_failures = 0
                self.error_occurred.emit(self._strings.get("could_not_catch"))
                self.status_changed.emit(self._strings.get("ready"))
            except Exception as exc:
                LOGGER.exception("worker_error", extra={"event_data": {"message": str(exc)}})
                self.error_occurred.emit(str(exc))
                self.status_changed.emit(self._strings.get("ready"))
                time.sleep(1)
        self.finished.emit()

    def stop(self) -> None:
        self._running = False
