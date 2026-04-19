from __future__ import annotations

from typing import Sequence

import pytest

from jarvis.implementations.llm.local_llm import LocalLLM
from jarvis.models.chat_turn import ChatTurn
from jarvis.services.lmstudio_service import (
    ChatMessage,
    LMStudioError,
    LMStudioService,
    LMStudioUnavailableError,
)


class FakeLMStudioService(LMStudioService):
    def __init__(self, response: str = "", raise_exc: Exception | None = None) -> None:
        self._response = response
        self._raise = raise_exc
        self.chat_calls: list[list[ChatMessage]] = []

    @property
    def model(self) -> str:
        return "fake"

    @property
    def base_url(self) -> str:
        return "http://fake"

    def ping(self) -> bool:
        return True

    def chat(
        self,
        messages: Sequence[ChatMessage],
        temperature: float = 0.1,
        max_tokens: int | None = None,
    ) -> str:
        self.chat_calls.append(list(messages))
        if self._raise is not None:
            raise self._raise
        return self._response


def test_decide_returns_action_from_valid_json() -> None:
    service = FakeLMStudioService(
        response='{"type":"action","app":"spotify","action":"open_app","parameters":{"target":"spotify"},"spoken_response":"Abrindo."}'
    )
    llm = LocalLLM(service=service)

    decision = llm.decide("abre o spotify")

    assert decision.type == "action"
    assert decision.action == "open_app"
    assert decision.spoken_response == "Abrindo."


def test_decide_falls_back_when_lmstudio_unavailable() -> None:
    service = FakeLMStudioService(raise_exc=LMStudioUnavailableError("refused"))
    llm = LocalLLM(service=service)

    decision = llm.decide("qualquer coisa")

    assert decision.type == "chat"
    assert "LM Studio" in decision.spoken_response


def test_decide_falls_back_on_generic_error() -> None:
    service = FakeLMStudioService(raise_exc=LMStudioError("boom"))
    llm = LocalLLM(service=service)

    decision = llm.decide("qualquer coisa")

    assert decision.type == "chat"
    assert "processar" in decision.spoken_response.lower()


def test_decide_falls_back_on_unparseable_output() -> None:
    service = FakeLMStudioService(response="this is not json")
    llm = LocalLLM(service=service)

    decision = llm.decide("qualquer coisa")

    assert decision.type == "chat"
    assert "entender" in decision.spoken_response.lower()


def test_decide_passes_history_as_chat_messages() -> None:
    service = FakeLMStudioService(
        response='{"type":"chat","spoken_response":"ok"}'
    )
    llm = LocalLLM(service=service, history_turns=4)
    history = [
        ChatTurn(role="user", content="oi"),
        ChatTurn(role="assistant", content="olá"),
    ]

    llm.decide("tudo bem?", history=history)

    messages = service.chat_calls[0]
    # system + 2 history turns + 1 user = 4
    assert len(messages) == 4
    assert messages[0].role == "system"
    assert messages[1].role == "user" and messages[1].content == "oi"
    # Assistant turns are wrapped in the JSON envelope to prevent the
    # model from drifting to plain-text replies on the next turn.
    assert messages[2].role == "assistant"
    assert '"spoken_response": "olá"' in messages[2].content
    assert messages[3].role == "user"
    assert "tudo bem?" in messages[3].content


def test_decide_truncates_history_to_history_turns() -> None:
    service = FakeLMStudioService(response='{"type":"chat","spoken_response":"ok"}')
    llm = LocalLLM(service=service, history_turns=2)
    history = [ChatTurn(role="user", content=str(i)) for i in range(10)]

    llm.decide("oi", history=history)

    messages = service.chat_calls[0]
    # system + last 2 history turns + user
    assert len(messages) == 4
    assert messages[1].content == "8"
    assert messages[2].content == "9"
