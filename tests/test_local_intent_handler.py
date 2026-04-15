from __future__ import annotations

from datetime import datetime

from jarvis.config.strings import Strings
from jarvis.services.local_intent_handler import LocalIntentHandler


def test_local_intent_handler_returns_date_response_pt() -> None:
    handler = LocalIntentHandler(
        strings=Strings("pt-BR"),
        now_provider=lambda: datetime(2026, 4, 14, 15, 45),
    )
    assert handler.handle("Que dia é hoje?") == "Hoje é 14 de abril de 2026, senhor."


def test_local_intent_handler_returns_time_response_pt() -> None:
    handler = LocalIntentHandler(
        strings=Strings("pt-BR"),
        now_provider=lambda: datetime(2026, 4, 14, 15, 45),
    )
    assert handler.handle("Que horas são?") == "Agora são 15:45, senhor."


def test_local_intent_handler_returns_date_response_en() -> None:
    handler = LocalIntentHandler(
        strings=Strings("en-US"),
        now_provider=lambda: datetime(2026, 4, 14, 15, 45),
    )
    assert handler.handle("What day is today?") == "Today is April 14, 2026, sir."


def test_local_intent_handler_returns_none_for_non_local_query() -> None:
    handler = LocalIntentHandler(strings=Strings("pt-BR"))
    assert handler.handle("Explique computação quântica.") is None
