from __future__ import annotations

import json
from typing import Any

from jarvis.implementations.llm.ollama_llm import OllamaLLM
from jarvis.models.llm_decision import LLMDecision


def _make_transport(content: str) -> tuple[list[dict[str, Any]], Any]:
    calls: list[dict[str, Any]] = []

    def transport(url: str, payload: dict[str, Any]) -> dict[str, Any]:
        calls.append({"url": url, "payload": payload})
        return {"message": {"role": "assistant", "content": content}, "done": True}

    return calls, transport


def test_ollama_decide_parses_action_payload() -> None:
    content = json.dumps(
        {
            "type": "action",
            "app": "spotify",
            "action": "play_spotify",
            "parameters": {"target": "coldplay"},
            "spoken_response": "Tocando Coldplay no Spotify.",
        }
    )
    calls, transport = _make_transport(content)
    llm = OllamaLLM(host="http://localhost:11434", model="qwen2.5:3b", transport=transport)

    decision = llm.decide("toca uma musica do coldplay")

    assert isinstance(decision, LLMDecision)
    assert decision.type == "action"
    assert decision.is_action is True
    assert decision.action == "play_spotify"
    assert decision.app == "spotify"
    assert decision.parameters == {"target": "coldplay"}
    assert decision.spoken_response == "Tocando Coldplay no Spotify."

    assert calls[0]["url"] == "http://localhost:11434/api/chat"
    assert calls[0]["payload"]["model"] == "qwen2.5:3b"
    assert calls[0]["payload"]["format"] == "json"
    assert calls[0]["payload"]["stream"] is False


def test_ollama_decide_parses_chat_payload() -> None:
    content = json.dumps(
        {
            "type": "chat",
            "app": None,
            "action": None,
            "parameters": {},
            "spoken_response": "Bom dia! Como posso ajudar?",
        }
    )
    _, transport = _make_transport(content)
    llm = OllamaLLM(transport=transport)

    decision = llm.decide("bom dia jarvis")

    assert decision.type == "chat"
    assert decision.is_action is False
    assert decision.app is None
    assert decision.action is None
    assert decision.spoken_response == "Bom dia! Como posso ajudar?"


def test_ollama_decide_falls_back_to_chat_when_json_invalid() -> None:
    _, transport = _make_transport("not a json at all")
    llm = OllamaLLM(transport=transport)

    decision = llm.decide("algo estranho")

    assert decision.type == "chat"
    assert decision.spoken_response


def test_ollama_decide_downgrades_action_without_action_field() -> None:
    content = json.dumps(
        {
            "type": "action",
            "app": "spotify",
            "action": None,
            "parameters": {},
            "spoken_response": "Beleza.",
        }
    )
    _, transport = _make_transport(content)
    llm = OllamaLLM(transport=transport)

    decision = llm.decide("oi")

    assert decision.type == "chat"
    assert decision.is_action is False


def test_ollama_decide_handles_transport_error() -> None:
    def failing_transport(url: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("connection refused")

    llm = OllamaLLM(transport=failing_transport)
    decision = llm.decide("oi")

    assert decision.type == "chat"
    assert decision.spoken_response


def test_ollama_interpret_returns_spoken_response() -> None:
    content = json.dumps(
        {
            "type": "chat",
            "app": None,
            "action": None,
            "parameters": {},
            "spoken_response": "Olá!",
        }
    )
    _, transport = _make_transport(content)
    llm = OllamaLLM(transport=transport)

    assert llm.interpret("oi") == "Olá!"
