"""Performance instrumentation toolkit: trace IDs, timed blocks, category tags.

Design goals:

- **One API for the whole pipeline**. Every stage (STT, LLM, TTS, executor,
  ...) emits logs through the same surface, so the human-readable terminal
  output and the JSON log file stay consistent.

- **Automatic trace propagation**. A single contextvar carries the trace_id
  so downstream code (deep in Piper, Qwen, or Spotify) doesn't need to
  thread an argument through every function to appear in the same trace.

- **Zero-cost decoration**. `timed()` is a context manager; it reads
  `time.perf_counter` twice and logs once. No external deps.

Usage:

    from jarvis.utils.performance import Category, new_trace_id, trace_context, timed, log, perf_log

    with trace_context():                       # auto-generates an ID
        with timed(Category.STT, "transcribe"):
            text = stt.transcribe(audio)
        log(Category.STT, f"transcribed: {text!r}")

The `Category` constants exist so miswritten tags ("stt" vs "STT") fail
at import time instead of silently producing a log noone can grep for.
"""

from __future__ import annotations

import logging
import secrets
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator


class Category:
    """Namespace of allowed log categories. Keep this list small — each
    entry is a coordinate you can grep for across the whole codebase."""

    SYSTEM = "SYSTEM"
    VOICE = "VOICE"       # audio capture + microphone plumbing
    STT = "STT"           # speech-to-text providers (Whisper, Google)
    LLM = "LLM"           # decision model (LocalLLM + LM Studio)
    PARSER = "PARSER"     # llm response parsing into a decision
    EXECUTOR = "EXECUTOR" # action execution (Spotify, Discord, Browser, ...)
    TTS = "TTS"           # synthesizer + audio playback
    PERF = "PERF"         # pure timing / performance lines
    TRACE = "TRACE"       # trace-level lifecycle events (start/end of a turn)


# Separate context vars so we can clear/set each independently.
# None means "not inside a trace" — callers shouldn't crash, they just
# emit logs without a trace prefix.
_current_trace: ContextVar[str | None] = ContextVar("jarvis_trace_id", default=None)
_current_category: ContextVar[str | None] = ContextVar("jarvis_category", default=None)

_PERF_LOGGER = logging.getLogger("jarvis.perf")


def new_trace_id() -> str:
    """Short, readable, collision-resistant enough for a session's worth of
    traces. 8 hex chars = 4 bytes = ~4B unique IDs; chance of collision in
    a session of thousands of turns is negligible."""
    return secrets.token_hex(4)


def current_trace_id() -> str | None:
    return _current_trace.get()


def current_category() -> str | None:
    return _current_category.get()


@contextmanager
def trace_context(trace_id: str | None = None) -> Iterator[str]:
    """Bind a trace_id to the current async/thread context for the block's
    duration. All `log`, `perf_log`, and `timed` calls inside inherit it
    automatically — no need to pass trace_id through function signatures.

    Yields the trace_id so the caller can log it or thread it across
    threads manually (contextvars don't cross thread boundaries).
    """
    tid = trace_id or new_trace_id()
    token = _current_trace.set(tid)
    try:
        yield tid
    finally:
        _current_trace.reset(token)


@contextmanager
def category_context(category: str) -> Iterator[None]:
    """Scope a category to a block. Useful when an entire service should
    default to one category without repeating it on every log call."""
    token = _current_category.set(category)
    try:
        yield
    finally:
        _current_category.reset(token)


@contextmanager
def timed(
    category: str,
    event: str,
    logger: logging.Logger | None = None,
    **extra: object,
) -> Iterator[dict[str, object]]:
    """Measure the wrapped block and emit a [PERF] log when it exits.

    Yields a mutable dict the caller can add fields to — handy for
    recording the size of a response, a character count, success flag,
    etc. that would otherwise require a separate log line.

        with timed(Category.LLM, "decide") as m:
            resp = model.chat(prompt)
            m["chars_out"] = len(resp)
    """
    log_target = logger or _PERF_LOGGER
    t0 = time.perf_counter()
    data: dict[str, object] = dict(extra)
    try:
        yield data
    finally:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        data["duration_ms"] = duration_ms
        log_target.info(
            event,
            extra={
                "category": category,
                "perf": True,
                "event_data": data,
            },
        )


def log(
    category: str,
    message: str,
    logger: logging.Logger | None = None,
    level: int = logging.INFO,
    **data: object,
) -> None:
    """Emit an informational log tagged with a category. Use for
    non-timing events: "STT transcribed: ...", "LLM raw response ...",
    "EXECUTOR command=play_spotify target=...".
    """
    log_target = logger or _PERF_LOGGER
    log_target.log(
        level,
        message,
        extra={
            "category": category,
            "event_data": data or {},
        },
    )


def perf_log(
    category: str,
    event: str,
    duration_ms: int,
    logger: logging.Logger | None = None,
    **data: object,
) -> None:
    """Emit a [PERF] line when you've measured timing yourself and just
    want to record it. For cases where `timed()` doesn't fit (e.g., the
    measurement spans a signal emit / slot invocation)."""
    log_target = logger or _PERF_LOGGER
    payload: dict[str, object] = {"duration_ms": duration_ms}
    payload.update(data)
    log_target.info(
        event,
        extra={
            "category": category,
            "perf": True,
            "event_data": payload,
        },
    )
