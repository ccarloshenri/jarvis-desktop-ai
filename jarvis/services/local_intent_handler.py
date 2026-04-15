from __future__ import annotations

import re
from datetime import datetime
from typing import Callable

from jarvis.config.strings import Strings


_MONTHS_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


class LocalIntentHandler:
    def __init__(
        self,
        strings: Strings | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._strings = strings or Strings()
        self._now_provider = now_provider or datetime.now

    def handle(self, text: str) -> str | None:
        normalized = self._normalize(text)
        if not normalized:
            return None
        if self._matches(normalized, ("que dia e hoje", "que dia e", "what day is today", "what is the date")):
            return self._strings.get("date_answer", date=self._format_date())
        if self._matches(normalized, ("que horas sao", "que horas", "what time is it", "tell me the time")):
            return self._strings.get("time_answer", time=self._format_time())
        if self._matches(normalized, ("clima", "chover", "tempo hoje", "weather", "rain")):
            return self._strings.get("weather_unavailable")
        return None

    def _normalize(self, text: str) -> str:
        lowered = text.lower().translate(
            str.maketrans("áàâãäéèêëíìîïóòôõöúùûüç", "aaaaaeeeeiiiiooooouuuuc")
        )
        return " ".join(re.sub(r"[^\w\s]", " ", lowered).split())

    def _matches(self, text: str, phrases: tuple[str, ...]) -> bool:
        return any(phrase in text for phrase in phrases)

    def _format_date(self) -> str:
        now = self._now_provider()
        if self._strings.language == "pt-BR":
            month = _MONTHS_PT[now.month - 1]
            return f"{now.day} de {month} de {now.year}"
        return now.strftime("%B %d, %Y")

    def _format_time(self) -> str:
        now = self._now_provider()
        if self._strings.language == "pt-BR":
            return now.strftime("%H:%M")
        return now.strftime("%I:%M %p").lstrip("0")
