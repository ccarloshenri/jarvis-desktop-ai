from __future__ import annotations

import logging
from typing import Sequence

from openai import AuthenticationError, OpenAI, RateLimitError

from jarvis.implementations.llm.decision_prompt import (
    DECISION_SYSTEM_PROMPT,
    build_user_message,
    parse_decision,
)
from jarvis.interfaces.illm import ILLM
from jarvis.models.chat_turn import ChatTurn
from jarvis.models.llm_decision import LLMDecision

LOGGER = logging.getLogger(__name__)


class GPTLLM(ILLM):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini", client: OpenAI | None = None) -> None:
        self._client = client or OpenAI(api_key=api_key, max_retries=1)
        self._model = model

    def interpret(self, text: str) -> str:
        return self.decide(text).spoken_response

    def decide(self, text: str, history: Sequence[ChatTurn] | None = None) -> LLMDecision:
        messages: list[dict[str, str]] = [{"role": "system", "content": DECISION_SYSTEM_PROMPT}]
        for turn in history or ():
            messages.append({"role": turn.role, "content": turn.content})
        messages.append({"role": "user", "content": build_user_message(text)})
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=messages,
            )
        except RateLimitError as exc:
            message = str(exc).lower()
            if "insufficient_quota" in message or "exceeded your current quota" in message:
                LOGGER.info("gpt_quota_exceeded")
                return LLMDecision(
                    type="chat",
                    spoken_response="Sua conta OpenAI está sem créditos. Troque de provedor nas configurações, senhor.",
                )
            LOGGER.warning("gpt_rate_limited", extra={"event_data": {"error": str(exc)}})
            return LLMDecision(
                type="chat",
                spoken_response="A OpenAI está limitando as requisições. Tente novamente em instantes, senhor.",
            )
        except AuthenticationError as exc:
            LOGGER.warning("gpt_auth_failed", extra={"event_data": {"error": str(exc)}})
            return LLMDecision(
                type="chat",
                spoken_response="A chave da OpenAI foi rejeitada. Reconecte nas configurações, senhor.",
            )
        except Exception as exc:
            LOGGER.warning("gpt_request_failed", extra={"event_data": {"error": str(exc)}})
            return LLMDecision(type="chat", spoken_response="Desculpe, não consegui processar agora.")

        content = self._extract_content(response)
        decision = parse_decision(content)
        if decision is None:
            LOGGER.warning("gpt_parse_failed", extra={"event_data": {"content": content[:400]}})
            return LLMDecision(type="chat", spoken_response=content.strip() or "Não entendi.")
        return decision

    def _extract_content(self, response: object) -> str:
        try:
            choices = getattr(response, "choices", None) or []
            if not choices:
                return ""
            message = getattr(choices[0], "message", None)
            content = getattr(message, "content", None) if message is not None else None
            return content.strip() if isinstance(content, str) else ""
        except Exception:
            return ""
