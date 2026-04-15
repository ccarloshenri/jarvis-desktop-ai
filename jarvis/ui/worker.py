from __future__ import annotations

import logging
import time

import speech_recognition as sr
from PySide6.QtCore import QObject, Signal

from jarvis.config.strings import Strings
from jarvis.interfaces.ispeech_to_text import ISpeechToText
from jarvis.services.assistant_service import AssistantService

LOGGER = logging.getLogger(__name__)


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
    ) -> None:
        super().__init__()
        self._strings = strings
        self._speech_to_text = speech_to_text
        self._assistant_service = assistant_service
        self._running = True

    def run(self) -> None:
        while self._running:
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
                continue
            except sr.UnknownValueError:
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
