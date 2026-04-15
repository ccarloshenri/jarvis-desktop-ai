from __future__ import annotations

import re
from datetime import datetime
from typing import Callable


class LocalIntentHandler:
    def __init__(self, now_provider: Callable[[], datetime] | None = None) -> None:
        self._now_provider = now_provider or datetime.now

    def handle(self, text: str) -> str | None:
        normalized = self._normalize(text)
        if self._is_date_query(normalized):
            return f"Today is {self._now_provider().strftime('%B %d, %Y')}, sir."
        if self._is_time_query(normalized):
            return f"It is currently {self._now_provider().strftime('%I:%M %p').lstrip('0')}, sir."
        if self._is_weather_query(normalized):
            return "I cannot check weather without internet access, sir."
        return None

    def _normalize(self, text: str) -> str:
        return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())

    def _is_date_query(self, text: str) -> bool:
        return any(phrase in text for phrase in ("what day is today", "what is the date today", "que dia e hoje", "que dia é hoje"))

    def _is_time_query(self, text: str) -> bool:
        return any(phrase in text for phrase in ("what time is it", "tell me the time", "que horas sao", "que horas são"))

    def _is_weather_query(self, text: str) -> bool:
        return "weather" in text or "rain" in text or "clima" in text or "chover" in text
