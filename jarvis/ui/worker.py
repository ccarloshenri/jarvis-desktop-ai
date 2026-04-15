from __future__ import annotations

import logging
import time

import speech_recognition as sr
from PySide6.QtCore import QObject, Signal

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

    def __init__(self, speech_to_text: ISpeechToText, assistant_service: AssistantService) -> None:
        super().__init__()
        self._speech_to_text = speech_to_text
        self._assistant_service = assistant_service
        self._running = True

    def run(self) -> None:
        while self._running:
            try:
                self.status_changed.emit("Listening")
                transcript = self._speech_to_text.listen()
                self.transcript_received.emit(transcript)
                self.status_changed.emit("Processing")
                result = self._assistant_service.process(transcript)
                self.command_processed.emit(result)
                self.response_ready.emit(result.spoken_response)
                self.status_changed.emit("Ready")
            except sr.WaitTimeoutError:
                continue
            except sr.UnknownValueError:
                self.error_occurred.emit("I couldn't catch that.")
                self.status_changed.emit("Ready")
            except Exception as exc:
                LOGGER.exception("worker_error", extra={"event_data": {"message": str(exc)}})
                self.error_occurred.emit(str(exc))
                self.status_changed.emit("Ready")
                time.sleep(1)
        self.finished.emit()

    def stop(self) -> None:
        self._running = False
