from __future__ import annotations

class ISpeechEvents:
    def emit_speaking_started(self, text: str) -> None:
        raise NotImplementedError

    def emit_speaking_finished(self, text: str) -> None:
        raise NotImplementedError
