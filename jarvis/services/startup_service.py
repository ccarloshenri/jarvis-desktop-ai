from __future__ import annotations

import logging
import threading
from typing import Callable

from jarvis.config.strings import Strings
from jarvis.interfaces.itext_to_speech import ITextToSpeech

LOGGER = logging.getLogger(__name__)


class StartupService:
    def __init__(
        self,
        strings: Strings,
        text_to_speech: ITextToSpeech,
        prefetch: Callable[[], None] | None = None,
    ) -> None:
        self._strings = strings
        self._text_to_speech = text_to_speech
        self._prefetch = prefetch

    def execute(self) -> None:
        if self._prefetch is not None:
            threading.Thread(target=self._safe_prefetch, name="jarvis-prefetch", daemon=True).start()
        self._text_to_speech.speak(self._strings.get("system_online"))

    def _safe_prefetch(self) -> None:
        try:
            self._prefetch()
        except Exception:
            LOGGER.exception("prefetch_failed")
