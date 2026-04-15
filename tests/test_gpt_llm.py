from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from jarvis.implementations.llm.gpt_llm import GPTLLM
from jarvis.models.llm_decision import LLMDecision


@dataclass
class _Message:
    content: str


@dataclass
class _Choice:
    message: _Message


@dataclass
class _Response:
    choices: list[_Choice]


class _FakeCompletions:
    def __init__(self, content: str) -> None:
        self._content = content
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _Response:
        self.calls.append(kwargs)
        return _Response(choices=[_Choice(message=_Message(content=self._content))])


class _FakeChat:
    def __init__(self, content: str) -> None:
        self.completions = _FakeCompletions(content)


class _FakeOpenAI:
    def __init__(self, content: str) -> None:
        self.chat = _FakeChat(content)


def test_gpt_decide_parses_action_payload() -> None:
    content = json.dumps(
        {
            "type": "action",
            "app": "spotify",
            "action": "play_spotify",
            "parameters": {"target": "radiohead"},
            "spoken_response": "Tocando Radiohead no Spotify.",
        }
    )
    fake = _FakeOpenAI(content)
    llm = GPTLLM(api_key="sk-test", client=fake)  # type: ignore[arg-type]

    decision = llm.decide("toca radiohead")

    assert isinstance(decision, LLMDecision)
    assert decision.type == "action"
    assert decision.action == "play_spotify"
    assert decision.parameters == {"target": "radiohead"}
    assert decision.spoken_response == "Tocando Radiohead no Spotify."

    call = fake.chat.completions.calls[0]
    assert call["model"] == "gpt-4o-mini"
    assert call["response_format"] == {"type": "json_object"}
    assert call["temperature"] == 0


def test_gpt_decide_falls_back_on_invalid_json() -> None:
    fake = _FakeOpenAI("nope not json")
    llm = GPTLLM(api_key="sk-test", client=fake)  # type: ignore[arg-type]

    decision = llm.decide("alo")

    assert decision.type == "chat"
    assert decision.spoken_response


def test_gpt_interpret_delegates_to_decide() -> None:
    content = json.dumps(
        {
            "type": "chat",
            "app": None,
            "action": None,
            "parameters": {},
            "spoken_response": "Olá, senhor.",
        }
    )
    fake = _FakeOpenAI(content)
    llm = GPTLLM(api_key="sk-test", client=fake)  # type: ignore[arg-type]

    assert llm.interpret("oi") == "Olá, senhor."
