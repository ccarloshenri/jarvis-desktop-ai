from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Iterator, Union

from jarvis.models.llm_decision import LLMDecision

LOGGER = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)
_MARKDOWN_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
# Matches the start of the `"spoken_response":"` field, including flexible
# whitespace around the colon. The capture group is unused — we only need
# `match.end()` to locate the first character inside the string value.
_SPOKEN_FIELD_START_RE = re.compile(r'"spoken_response"\s*:\s*"')
# Sentence-ender followed by whitespace. We don't split on trailing `.` at
# the end of the buffer because more text may still arrive (e.g. "Dr." is
# not a sentence end if the next token is "Souza").
_SENTENCE_BOUNDARY_RE = re.compile(r"([.!?…]+)(\s+)")


def parse_decision(raw: str) -> LLMDecision | None:
    """Extract an LLMDecision from raw model output.

    Small local models (Qwen 2.5 3B) routinely drift: trailing explanations,
    markdown fences, or multiple JSON attempts. This parser is intentionally
    forgiving — strip obvious junk, grab the widest {...} block, then validate.
    Returns None when the raw output can't be salvaged, letting the caller
    decide how to fall back (usually a generic "não entendi" message).
    """
    if not raw:
        return None
    candidate = _MARKDOWN_FENCE_RE.sub("", raw.strip())
    match = _JSON_BLOCK_RE.search(candidate)
    if match:
        candidate = match.group(0)
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:
        LOGGER.warning(
            "llm_parse_json_failed",
            extra={"event_data": {"error": str(exc), "raw": raw[:400]}},
        )
        return None
    if not isinstance(data, dict):
        return None

    decision_type = str(data.get("type", "chat")).strip().lower()
    if decision_type not in ("action", "chat"):
        decision_type = "chat"

    spoken = str(data.get("spoken_response") or "").strip()
    if not spoken:
        return None

    app_value = data.get("app")
    app = (
        str(app_value).strip().lower()
        if isinstance(app_value, str) and app_value.strip()
        else None
    )

    action_value = data.get("action")
    action = (
        str(action_value).strip().lower()
        if isinstance(action_value, str) and action_value.strip()
        else None
    )

    parameters_value = data.get("parameters")
    parameters = parameters_value if isinstance(parameters_value, dict) else {}

    if decision_type == "action" and not action:
        # Model said "action" but left the field empty — treat as chat so we
        # at least speak the response instead of silently dropping the turn.
        decision_type = "chat"

    return LLMDecision(
        type=decision_type,  # type: ignore[arg-type]
        spoken_response=spoken,
        app=app,
        action=action,
        parameters=parameters,
    )


@dataclass(frozen=True, slots=True)
class SpokenChunk:
    """Ready-to-speak fragment of `spoken_response`, chunked at a sentence
    boundary. The consumer hands this straight to the TTS pipeline."""

    text: str


@dataclass(frozen=True, slots=True)
class ActionReady:
    """Action + parameters have been fully streamed and the executor can
    start running in parallel with any remaining `spoken_response` tokens.

    `app` and `decision_type` are included so the consumer can reproduce
    the same validation as the non-streaming path.
    """

    decision_type: str
    app: str | None
    action: str
    parameters: dict


@dataclass(frozen=True, slots=True)
class ParseComplete:
    """Final event. `decision` is the fully validated LLMDecision, or None
    if the buffered JSON could not be salvaged (mirrors `parse_decision`)."""

    decision: LLMDecision | None


StreamEvent = Union[SpokenChunk, ActionReady, ParseComplete]


class StreamingDecisionParser:
    """Incrementally parse the LLM's streaming JSON output.

    The model's contract (see DECISION_SYSTEM_PROMPT in local_llm.py) puts
    `spoken_response` last, so by the time we see its opening quote we
    already have `type`, `app`, `action`, and `parameters` committed to
    the buffer. That ordering is the load-bearing assumption here — if
    it changes, `ActionReady` would fire late (or not at all before the
    parse completes), but `SpokenChunk`s would still stream correctly.

    Call `feed(delta)` for each chunk from `chat_stream`. Call `finalize()`
    exactly once at the end of the stream; it flushes any pending spoken
    text and yields the final `ParseComplete`. Do NOT call `feed` after
    `finalize`.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._spoken_value_start: int | None = None  # index after the `"`
        self._pending = ""  # unescaped text not yet emitted
        self._unescaped_consumed = 0  # total unescaped chars already drained into pending
        self._spoken_done = False
        self._action_emitted = False

    def feed(self, delta: str) -> Iterator[StreamEvent]:
        if not delta:
            return
        self._buffer += delta

        # Detect the entry point into the spoken_response string value.
        # Before this fires, all action-related fields are fully present
        # in the buffer (per the prompt's field ordering), so we can emit
        # ActionReady right away without waiting for the whole JSON.
        if self._spoken_value_start is None:
            m = _SPOKEN_FIELD_START_RE.search(self._buffer)
            if m:
                self._spoken_value_start = m.end()
                if not self._action_emitted:
                    event = self._try_build_action_ready(m.start())
                    if event is not None:
                        self._action_emitted = True
                        yield event

        if self._spoken_value_start is not None and not self._spoken_done:
            unescaped, _consumed, ended = _decode_json_string_prefix(
                self._buffer, self._spoken_value_start
            )
            if len(unescaped) > self._unescaped_consumed:
                self._pending += unescaped[self._unescaped_consumed:]
                self._unescaped_consumed = len(unescaped)
                while True:
                    m = _SENTENCE_BOUNDARY_RE.search(self._pending)
                    if m is None:
                        break
                    # Include the punctuation; drop the trailing whitespace
                    # that triggered the boundary.
                    chunk = self._pending[: m.end(1)].strip()
                    self._pending = self._pending[m.end():]
                    if chunk:
                        yield SpokenChunk(chunk)
            if ended:
                self._spoken_done = True

    def finalize(self) -> Iterator[StreamEvent]:
        # Flush any trailing spoken_response text that didn't hit a sentence
        # boundary. For short (1-sentence) responses this is the only chunk
        # the consumer ever sees — the sentence ender is at the very end of
        # the string and feed() never triggered a boundary split.
        if self._pending.strip():
            chunk = self._pending.strip()
            self._pending = ""
            yield SpokenChunk(chunk)
        yield ParseComplete(parse_decision(self._buffer))

    @property
    def buffer(self) -> str:
        """Raw accumulated model output. Exposed so callers can log it
        alongside the trace without owning a second copy of the string."""
        return self._buffer

    def _try_build_action_ready(self, field_pos: int) -> ActionReady | None:
        # Synthesize a complete JSON document by appending a placeholder
        # spoken_response so parse_decision treats the partial as valid.
        # (It rejects empty spoken strings, hence the sentinel — which we
        # strip off before constructing the event.)
        head = self._buffer[:field_pos].rstrip().rstrip(",")
        if not head.lstrip().startswith("{"):
            # Preamble is corrupt or not JSON-shaped — give up and let
            # the non-streaming parse pick up the pieces at finalize().
            return None
        stub = head + ',"spoken_response":"_"}'
        decision = parse_decision(stub)
        if decision is None or not decision.action:
            return None
        return ActionReady(
            decision_type=decision.type,
            app=decision.app,
            action=decision.action,
            parameters=dict(decision.parameters or {}),
        )


def _decode_json_string_prefix(buffer: str, start: int) -> tuple[str, int, bool]:
    r"""Decode the JSON string value starting at ``buffer[start]`` (right after
    the opening quote) as far as possible.

    Returns ``(unescaped_text, consumed_chars_in_buffer, ended)``:

    - ``unescaped_text`` is the accumulated value so far, with JSON escapes
      resolved (``\"``, ``\\``, ``\n``, ``\t``, ``\uXXXX``).
    - ``consumed_chars_in_buffer`` is how many buffer chars belong to the
      value — useful for moving past the closing quote downstream.
    - ``ended`` is True when the closing unescaped quote was reached; False
      means more characters are still expected.

    If an escape sequence is split across buffer boundaries (e.g. the last
    char is ``\\`` with no follow-up yet), we stop *before* the backslash
    so the next feed() can resume cleanly.
    """
    out_chars: list[str] = []
    i = start
    n = len(buffer)
    while i < n:
        ch = buffer[i]
        if ch == '"':
            return "".join(out_chars), i - start, True
        if ch == "\\":
            if i + 1 >= n:
                # Escape split across feeds — wait for more input before
                # consuming the backslash.
                break
            esc = buffer[i + 1]
            mapped = _JSON_ESCAPE_MAP.get(esc)
            if mapped is not None:
                out_chars.append(mapped)
                i += 2
                continue
            if esc == "u":
                if i + 6 > n:
                    # \uXXXX split across feeds — wait for the full hex.
                    break
                hex_part = buffer[i + 2 : i + 6]
                try:
                    out_chars.append(chr(int(hex_part, 16)))
                except ValueError:
                    out_chars.append(esc)  # fall back, don't crash the stream
                i += 6
                continue
            # Unknown escape — keep the literal char, skip the backslash.
            out_chars.append(esc)
            i += 2
            continue
        out_chars.append(ch)
        i += 1
    return "".join(out_chars), i - start, False


_JSON_ESCAPE_MAP = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "b": "\b",
    "f": "\f",
}


