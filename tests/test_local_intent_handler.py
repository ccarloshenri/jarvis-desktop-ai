from __future__ import annotations

from datetime import datetime

from jarvis.services.local_intent_handler import LocalIntentHandler


def test_local_intent_handler_returns_date_response() -> None:
    handler = LocalIntentHandler(now_provider=lambda: datetime(2026, 4, 14, 15, 45))
    assert handler.handle("Que dia é hoje?") == "Today is April 14, 2026, sir."


def test_local_intent_handler_returns_time_response() -> None:
    handler = LocalIntentHandler(now_provider=lambda: datetime(2026, 4, 14, 15, 45))
    assert handler.handle("What time is it?") == "It is currently 3:45 PM, sir."


def test_local_intent_handler_returns_none_for_non_local_query() -> None:
    handler = LocalIntentHandler()
    assert handler.handle("Explain quantum computing.") is None
