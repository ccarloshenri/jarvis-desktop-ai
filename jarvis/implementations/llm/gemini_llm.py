from __future__ import annotations

import logging
from typing import Any

import google.generativeai as genai

from jarvis.implementations.llm.decision_prompt import DECISION_SYSTEM_PROMPT, parse_decision
from jarvis.interfaces.illm import ILLM
from jarvis.models.llm_decision import LLMDecision

LOGGER = logging.getLogger(__name__)


class GeminiLLM(ILLM):
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        client: Any | None = None,
    ) -> None:
        if client is not None:
            self._model = client
        else:
            genai.configure(api_key=api_key)
            self._model = genai.GenerativeModel(
                model_name=model,
                system_instruction=DECISION_SYSTEM_PROMPT,
            )

    def interpret(self, text: str) -> str:
        return self.decide(text).spoken_response

    def decide(self, text: str) -> LLMDecision:
        try:
            response = self._model.generate_content(
                text.strip(),
                generation_config={
                    "temperature": 0,
                    "response_mime_type": "application/json",
                },
            )
        except Exception as exc:
            return self._handle_error(exc)

        content = self._extract_text(response)
        decision = parse_decision(content)
        if decision is None:
            LOGGER.warning("gemini_parse_failed", extra={"event_data": {"content": content[:400]}})
            return LLMDecision(type="chat", spoken_response=content.strip() or "Não entendi.")
        return decision

    def _extract_text(self, response: Any) -> str:
        try:
            text = getattr(response, "text", None)
            if isinstance(text, str):
                return text
        except Exception:
            pass
        try:
            candidates = getattr(response, "candidates", None) or []
            for candidate in candidates:
                content = getattr(candidate, "content", None)
                parts = getattr(content, "parts", None) or []
                for part in parts:
                    value = getattr(part, "text", None)
                    if isinstance(value, str) and value:
                        return value
        except Exception:
            pass
        return ""

    def _handle_error(self, exc: Exception) -> LLMDecision:
        message = str(exc).lower()
        if "not found" in message or "is not supported" in message:
            LOGGER.warning("gemini_model_not_found", extra={"event_data": {"error": str(exc)}})
            return LLMDecision(
                type="chat",
                spoken_response="O modelo do Gemini não está disponível. Troque de provedor nas configurações, senhor.",
            )
        if "permission" in message or "api key" in message or "unauthenticated" in message:
            LOGGER.warning("gemini_auth_failed", extra={"event_data": {"error": str(exc)}})
            return LLMDecision(
                type="chat",
                spoken_response="A chave do Gemini foi rejeitada. Reconecte nas configurações, senhor.",
            )
        if "quota" in message or "rate" in message:
            LOGGER.info("gemini_quota_or_rate_limit", extra={"event_data": {"error": str(exc)}})
            return LLMDecision(
                type="chat",
                spoken_response="O Gemini está limitando as requisições. Tente novamente em instantes, senhor.",
            )
        LOGGER.warning("gemini_request_failed", extra={"event_data": {"error": str(exc)}})
        return LLMDecision(type="chat", spoken_response="Desculpe, não consegui processar agora.")
