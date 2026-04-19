from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Iterator, Sequence

import requests

from jarvis.utils.performance import Category, log, perf_log

LOGGER = logging.getLogger(__name__)


class LMStudioError(Exception):
    """LM Studio request failed — connection, HTTP, or timeout."""


class LMStudioUnavailableError(LMStudioError):
    """LM Studio is not reachable (connection refused, unreachable host)."""


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


class LMStudioService:
    """Thin HTTP client for an OpenAI-compatible chat completions API.

    Name is historical — started as LM-Studio-only. Now also drives Groq
    (same API shape at https://api.groq.com/openai/v1, requires Bearer
    auth). Business logic (prompt construction, response parsing,
    history management) belongs upstream in LocalLLM.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        model: str = "qwen2.5-3b-instruct",
        timeout_s: float = 30.0,
        api_key: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_s = timeout_s
        self._api_key = api_key or None

    @property
    def model(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    def ping(self) -> bool:
        """Quick health check: GET /v1/models. Used at boot so the UI can
        warn the user if the backend isn't reachable before they try to
        speak. Short timeout — this blocks startup."""
        try:
            response = requests.get(
                f"{self._base_url}/models",
                timeout=2.0,
                headers=self._auth_headers(),
            )
            return response.ok
        except requests.RequestException:
            return False

    def _auth_headers(self) -> dict[str, str]:
        if not self._api_key:
            return {}
        return {"Authorization": f"Bearer {self._api_key}"}

    def chat(
        self,
        messages: Sequence[ChatMessage],
        temperature: float = 0.1,
        max_tokens: int | None = None,
    ) -> str:
        """Send a chat completion request and return the assistant's raw text.

        Raises LMStudioUnavailableError if the server isn't running, or
        LMStudioError for other HTTP/timeout failures. The caller is
        responsible for parsing the content (which may be JSON-shaped).

        Note: LM Studio's current API rejects `response_format: json_object`
        with HTTP 400 ("must be 'json_schema' or 'text'"). We enforce JSON
        output via the system prompt + a forgiving parser instead; building
        a full JSON schema for every possible action here would be brittle.
        """
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        url = f"{self._base_url}/chat/completions"
        t0 = time.perf_counter()
        try:
            response = requests.post(
                url,
                json=payload,
                timeout=self._timeout_s,
                headers=self._auth_headers(),
            )
        except requests.ConnectionError as exc:
            raise LMStudioUnavailableError(str(exc)) from exc
        except requests.Timeout as exc:
            raise LMStudioError(f"timeout after {self._timeout_s}s") from exc
        except requests.RequestException as exc:
            raise LMStudioError(str(exc)) from exc

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        if not response.ok:
            log(
                Category.LLM,
                f"HTTP {response.status_code} after {elapsed_ms}ms: {response.text[:400]}",
                level=logging.WARNING,
            )
            raise LMStudioError(f"HTTP {response.status_code}: {response.text[:200]}")

        try:
            data = response.json()
        except ValueError as exc:
            raise LMStudioError(f"invalid JSON from LM Studio: {exc}") from exc

        choices = data.get("choices") or []
        if not choices:
            raise LMStudioError("empty choices in LM Studio response")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str):
            raise LMStudioError("missing content in LM Studio response")
        perf_log(
            Category.LLM,
            "lm studio round-trip",
            elapsed_ms,
            model=self._model,
            chars_out=len(content),
        )
        return content

    def chat_stream(
        self,
        messages: Sequence[ChatMessage],
        temperature: float = 0.1,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        """Stream chat completion deltas as they arrive from LM Studio.

        Yields `content` string chunks from `choices[0].delta.content` in
        order. Consumers can start processing the output (parse, speak,
        execute) while the model is still generating, which is the whole
        reason the streaming pipeline exists.

        Raises LMStudioUnavailableError if the server isn't reachable, or
        LMStudioError for HTTP/parse/timeout failures. Errors after the
        first token are raised mid-iteration — callers should handle
        StopIteration and exceptions with a try/except around the loop.
        """
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        url = f"{self._base_url}/chat/completions"
        t0 = time.perf_counter()
        try:
            response = requests.post(
                url,
                json=payload,
                timeout=self._timeout_s,
                stream=True,
                headers=self._auth_headers(),
            )
        except requests.ConnectionError as exc:
            raise LMStudioUnavailableError(str(exc)) from exc
        except requests.Timeout as exc:
            raise LMStudioError(f"timeout after {self._timeout_s}s") from exc
        except requests.RequestException as exc:
            raise LMStudioError(str(exc)) from exc

        if not response.ok:
            body = response.text[:400]
            response.close()
            log(
                Category.LLM,
                f"HTTP {response.status_code} on stream start: {body}",
                level=logging.WARNING,
            )
            raise LMStudioError(f"HTTP {response.status_code}: {body[:200]}")

        # SSE responses ship as `text/event-stream` with no charset, and
        # requests' iter_lines(decode_unicode=True) falls back to ISO-8859-1
        # per RFC 2616. Groq (and most OpenAI-compatible servers) actually
        # emit UTF-8 bytes there, which comes out as mojibake ("VocÃª" for
        # "Você") if we don't force the decoder.
        response.encoding = "utf-8"

        ttfb_ms: int | None = None
        total_chars = 0
        try:
            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                # OpenAI-compatible SSE: lines are `data: {...}` or `data: [DONE]`.
                # LM Studio sometimes omits the space after the colon; accept both.
                if raw_line.startswith("data: "):
                    data_str = raw_line[6:]
                elif raw_line.startswith("data:"):
                    data_str = raw_line[5:]
                else:
                    # Other event types (`event:`, `:heartbeat`) are safe to skip.
                    continue
                data_str = data_str.strip()
                if not data_str or data_str == "[DONE]":
                    if data_str == "[DONE]":
                        break
                    continue
                try:
                    event = json.loads(data_str)
                except json.JSONDecodeError:
                    # A malformed SSE frame mid-stream isn't fatal — drop it
                    # and keep reading. If the whole stream is malformed the
                    # iter_lines loop will just end with nothing yielded.
                    continue
                choices = event.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                content = delta.get("content")
                if isinstance(content, str) and content:
                    if ttfb_ms is None:
                        ttfb_ms = int((time.perf_counter() - t0) * 1000)
                        log(
                            Category.LLM,
                            "lm studio stream: first token",
                            ttfb_ms=ttfb_ms,
                        )
                    total_chars += len(content)
                    yield content
        finally:
            response.close()
            total_ms = int((time.perf_counter() - t0) * 1000)
            perf_log(
                Category.LLM,
                "lm studio stream",
                total_ms,
                model=self._model,
                chars_out=total_chars,
                ttfb_ms=ttfb_ms if ttfb_ms is not None else -1,
            )
