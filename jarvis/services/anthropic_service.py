"""Anthropic Messages API client.

Anthropic's schema differs from OpenAI-compatible endpoints in three
ways that force a dedicated client:

- Endpoint: `/v1/messages` (not `/v1/chat/completions`).
- Top-level system prompt is a separate `system` field instead of a
  role="system" message in the array.
- Streaming events are named SSE events (`event: content_block_delta`)
  rather than plain `data: {...}` frames; the delta lives at
  `event.delta.text`.

The class duck-types LMStudioService's `chat()` and `chat_stream()`
methods so LocalLLM can consume it without caring which backend it
hit. Same `ChatMessage` input, same str / Iterator[str] output.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Iterator, Sequence

import requests

from jarvis.services.lmstudio_service import (
    ChatMessage,
    LMStudioError,
    LMStudioUnavailableError,
)
from jarvis.utils.performance import Category, log, perf_log

LOGGER = logging.getLogger(__name__)


_DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
_API_VERSION = "2023-06-01"


class AnthropicService:
    """HTTP client for Anthropic's Messages API.

    Duck-typed to match `LMStudioService`: exposes `chat(messages,
    temperature, max_tokens)` → str and `chat_stream(...)` → iter of
    content deltas. LocalLLM depends on just those two methods, so
    swapping backends is a factory-level decision.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = _DEFAULT_BASE_URL,
        timeout_s: float = 30.0,
    ) -> None:
        if not api_key:
            raise LMStudioError("anthropic requires an api key")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    @property
    def model(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    def ping(self) -> bool:
        """Cheap reachability probe. Anthropic has no dedicated health
        endpoint, so we hit `/v1/models` and call 200/401 "reachable"
        (401 means our request made it, key is bad — still reachable)."""
        try:
            response = requests.get(
                f"{self._base_url}/models",
                timeout=2.0,
                headers=self._base_headers(),
            )
            return response.status_code < 500
        except requests.RequestException:
            return False

    def chat(
        self,
        messages: Sequence[ChatMessage],
        temperature: float = 0.1,
        max_tokens: int | None = None,
    ) -> str:
        payload = self._build_payload(messages, temperature, max_tokens, stream=False)
        t0 = time.perf_counter()
        try:
            response = requests.post(
                f"{self._base_url}/messages",
                json=payload,
                timeout=self._timeout_s,
                headers=self._base_headers(),
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
                f"anthropic HTTP {response.status_code} after {elapsed_ms}ms: {response.text[:400]}",
                level=logging.WARNING,
            )
            raise LMStudioError(f"HTTP {response.status_code}: {response.text[:200]}")

        try:
            data = response.json()
        except ValueError as exc:
            raise LMStudioError(f"invalid JSON: {exc}") from exc

        content_blocks = data.get("content") or []
        # Anthropic returns a list of content blocks (text / tool_use /
        # etc). We only care about the concatenated text blocks —
        # anything else a future assistant turn produces gets ignored
        # and logged.
        parts: list[str] = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        text = "".join(parts)
        perf_log(
            Category.LLM,
            "anthropic round-trip",
            elapsed_ms,
            model=self._model,
            chars_out=len(text),
        )
        return text

    def chat_stream(
        self,
        messages: Sequence[ChatMessage],
        temperature: float = 0.1,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        payload = self._build_payload(messages, temperature, max_tokens, stream=True)
        t0 = time.perf_counter()
        try:
            response = requests.post(
                f"{self._base_url}/messages",
                json=payload,
                timeout=self._timeout_s,
                stream=True,
                headers=self._base_headers(),
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
            raise LMStudioError(f"HTTP {response.status_code}: {body[:200]}")

        # Anthropic streams SSE with named events. Each message looks
        # like:
        #   event: content_block_delta
        #   data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"..."}}
        # We only emit text from `content_block_delta` / `text_delta`
        # deltas; all other event types (message_start, ping, etc) are
        # control frames we can skip.
        response.encoding = "utf-8"
        ttfb_ms: int | None = None
        total_chars = 0
        try:
            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                if raw_line.startswith("data:"):
                    data_str = raw_line[5:].strip()
                else:
                    continue
                if not data_str or data_str == "[DONE]":
                    if data_str == "[DONE]":
                        break
                    continue
                try:
                    event = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                if event.get("type") != "content_block_delta":
                    continue
                delta = event.get("delta") or {}
                if delta.get("type") != "text_delta":
                    continue
                piece = delta.get("text")
                if not isinstance(piece, str) or not piece:
                    continue
                if ttfb_ms is None:
                    ttfb_ms = int((time.perf_counter() - t0) * 1000)
                    log(
                        Category.LLM,
                        "anthropic stream: first token",
                        ttfb_ms=ttfb_ms,
                    )
                total_chars += len(piece)
                yield piece
        finally:
            response.close()
            total_ms = int((time.perf_counter() - t0) * 1000)
            perf_log(
                Category.LLM,
                "anthropic stream",
                total_ms,
                model=self._model,
                chars_out=total_chars,
                ttfb_ms=ttfb_ms if ttfb_ms is not None else -1,
            )

    def _build_payload(
        self,
        messages: Sequence[ChatMessage],
        temperature: float,
        max_tokens: int | None,
        *,
        stream: bool,
    ) -> dict[str, Any]:
        # Anthropic's messages payload wants `system` as a top-level
        # field (or list of blocks), and the `messages` array only
        # accepts user/assistant alternations. Map our ChatMessage
        # list through: the first system-role entry becomes `system`,
        # everything else goes into the array.
        system_text: str | None = None
        msg_array: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                # Concatenate multiple system messages with double
                # newlines — matches the convention Anthropic's own
                # client libraries use.
                system_text = (
                    f"{system_text}\n\n{m.content}" if system_text else m.content
                )
                continue
            msg_array.append({"role": m.role, "content": m.content})

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": msg_array,
            "temperature": temperature,
            "stream": stream,
            # Anthropic requires max_tokens; use the caller's value or
            # a sane default so short responses still cap cleanly.
            "max_tokens": max_tokens if max_tokens is not None else 512,
        }
        if system_text is not None:
            payload["system"] = system_text
        return payload

    def _base_headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        }
