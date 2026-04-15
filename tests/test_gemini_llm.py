from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from jarvis.implementations.llm.gemini_llm import GeminiLLM
from jarvis.models.llm_decision import LLMDecision


@dataclass
class _FakeResponse:
    text: str


class _FakeModel:
    def __init__(self, response_text: str) -> None:
        self._response_text = response_text
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, prompt: str, generation_config: dict[str, Any]) -> _FakeResponse:
        self.calls.append({"prompt": prompt, "generation_config": generation_config})
        return _FakeResponse(text=self._response_text)


class _FailingModel:
    def __init__(self, exception: Exception) -> None:
        self._exception = exception

    def generate_content(self, prompt: str, generation_config: dict[str, Any]) -> Any:
        raise self._exception


def test_gemini_decide_parses_action_payload() -> None:
    content = json.dumps(
        {
            "type": "action",
            "app": "spotify",
            "action": "play_spotify",
            "parameters": {"target": "radiohead"},
            "spoken_response": "Tocando Radiohead no Spotify.",
        }
    )
    fake = _FakeModel(content)
    llm = GeminiLLM(api_key="fake", client=fake)

    decision = llm.decide("toca radiohead")

    assert isinstance(decision, LLMDecision)
    assert decision.type == "action"
    assert decision.action == "play_spotify"
    assert decision.parameters == {"target": "radiohead"}
    assert decision.spoken_response == "Tocando Radiohead no Spotify."
    call = fake.calls[0]
    assert call["generation_config"]["response_mime_type"] == "application/json"
    assert call["generation_config"]["temperature"] == 0


def test_gemini_decide_handles_not_found_error() -> None:
    class NotFound(Exception):
        pass

    fake = _FailingModel(NotFound("404 models/gemini-1.5-flash is not found for API version v1beta"))
    llm = GeminiLLM(api_key="fake", client=fake)

    decision = llm.decide("oi")

    assert decision.type == "chat"
    assert "não está disponível" in decision.spoken_response.lower()


def test_gemini_decide_handles_auth_error() -> None:
    fake = _FailingModel(Exception("API key not valid. Please pass a valid API key."))
    llm = GeminiLLM(api_key="fake", client=fake)

    decision = llm.decide("oi")

    assert decision.type == "chat"
    assert "rejeitada" in decision.spoken_response.lower()


def test_gemini_decide_handles_quota_error() -> None:
    fake = _FailingModel(Exception("429 Quota exceeded for quota metric"))
    llm = GeminiLLM(api_key="fake", client=fake)

    decision = llm.decide("oi")

    assert decision.type == "chat"
    assert "limitando" in decision.spoken_response.lower()


def test_gemini_decide_falls_back_on_invalid_json() -> None:
    fake = _FakeModel("not a json at all")
    llm = GeminiLLM(api_key="fake", client=fake)

    decision = llm.decide("alo")

    assert decision.type == "chat"
    assert decision.spoken_response


def test_gemini_interpret_delegates_to_decide() -> None:
    content = json.dumps(
        {
            "type": "chat",
            "app": None,
            "action": None,
            "parameters": {},
            "spoken_response": "Olá, senhor.",
        }
    )
    fake = _FakeModel(content)
    llm = GeminiLLM(api_key="fake", client=fake)

    assert llm.interpret("oi") == "Olá, senhor."
