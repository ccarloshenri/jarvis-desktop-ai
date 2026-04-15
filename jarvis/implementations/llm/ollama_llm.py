from __future__ import annotations

import logging
from typing import Any, Callable

import requests

from jarvis.implementations.llm.decision_prompt import DECISION_SYSTEM_PROMPT, parse_decision
from jarvis.interfaces.illm import ILLM
from jarvis.models.llm_decision import LLMDecision

LOGGER = logging.getLogger(__name__)

Transport = Callable[[str, dict[str, Any]], dict[str, Any]]


class OllamaLLM(ILLM):
    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "qwen2.5:3b",
        timeout: float = 30.0,
        transport: Transport | None = None,
    ) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._transport = transport or self._default_transport

    def interpret(self, text: str) -> str:
        return self.decide(text).spoken_response

    def decide(self, text: str) -> LLMDecision:
        payload = {
            "model": self._model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": DECISION_SYSTEM_PROMPT},
                {"role": "user", "content": text.strip()},
            ],
        }
        try:
            response = self._transport(f"{self._host}/api/chat", payload)
        except Exception as exc:
            LOGGER.warning("ollama_request_failed", extra={"event_data": {"error": str(exc)}})
            return LLMDecision(type="chat", spoken_response="Desculpe, não consegui processar agora.")

        content = self._extract_content(response)
        decision = parse_decision(content)
        if decision is None:
            LOGGER.warning("ollama_parse_failed", extra={"event_data": {"content": content[:400]}})
            return LLMDecision(type="chat", spoken_response=content.strip() or "Não entendi.")
        return decision

    def _default_transport(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(url, json=payload, timeout=self._timeout)
        response.raise_for_status()
        return response.json()

    def _extract_content(self, response: dict[str, Any]) -> str:
        message = response.get("message") or {}
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content
        return ""
