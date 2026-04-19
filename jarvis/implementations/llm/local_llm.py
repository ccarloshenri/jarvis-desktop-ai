from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Iterator, Sequence

from jarvis.config.strings import Strings
from jarvis.interfaces.illm import ILLM
from jarvis.models.chat_turn import ChatTurn
from jarvis.models.llm_decision import LLMDecision
from jarvis.services.lmstudio_service import (
    ChatMessage,
    LMStudioError,
    LMStudioService,
    LMStudioUnavailableError,
)
from jarvis.utils.llm_response_parser import (
    ParseComplete,
    StreamEvent,
    StreamingDecisionParser,
    parse_decision,
)
from jarvis.utils.performance import Category, log, timed

LOGGER = logging.getLogger(__name__)


DECISION_SYSTEM_PROMPT = """You are Jarvis, Tony Stark's AI butler. Always reply in English, addressing the user as "sir". Output ONLY JSON: {"type":"action"|"chat","app":string|null,"action":string|null,"parameters":object,"spoken_response":string}

CLASSIFICATION:
- type="action" if the user uses a COMMAND verb: open, close, play, search, send, mute, join, leave, focus, next, previous, reload, show off, impress.
- type="chat" for everything else (questions, greetings, math, opinions, explanations, small talk).

spoken_response rules:
- action: ONE of these EXACT phrases, nothing else — "Opening.", "Closing.", "Playing.", "Searching.", "Searching YouTube.", "Searching images.", "Searching news.", "Opening the site.", "Opening the link.", "Done." (any browser action), "Done, sir." (any discord action), "Observe, sir." (show_off).
- chat: ANSWER the question in 1-2 natural English sentences. NEVER use the action ack phrases above in chat responses.

Actions (action / {parameters}):
open_app|close_app|play_spotify|search_web / {target}
browser_search_google|browser_search_youtube|browser_search_images|browser_search_news / {query}
browser_open_site / {site}; browser_open_url / {url}; browser_open_email / {filter:"inbox"|"unread"|"important"}
browser_search_email_from / {sender}; browser_search_email_subject / {subject}
browser_open|browser_close|browser_focus|browser_new_tab|browser_close_tab|browser_next_tab|browser_prev_tab|browser_back|browser_forward|browser_reload|browser_check_unread / {}
discord_open|discord_close|discord_focus|discord_toggle_mute|discord_toggle_deafen|discord_leave_voice|discord_previous / {}
discord_open_dm / {target_name}; discord_open_server / {server_name}; discord_open_channel / {channel_name,server_name?}
discord_send_message / {target_type:"dm"|"channel",target_name,channel_name?,server_name?,message}
discord_reply_current / {message}; discord_join_voice / {channel_name}
discord_set_status / {status:"online"|"idle"|"dnd"|"invisible",custom_text?}
show_off / {} — triggers on "show off", "impress me", "give me a show", "put on a show"
volume_up|volume_down|volume_mute / {} — system volume
screenshot / {} — capture current desktop
clipboard_read / {} — read and speak clipboard text
lock_screen / {} — lock the windows session
open_folder / {target} — target is a folder name (downloads, documents, desktop, pictures, music, videos) or a path

Use conversation history to resolve "it/that/there".

CHAT examples (real answer, NEVER an ack phrase):
"what day is it" → {"type":"chat","app":null,"action":null,"parameters":{},"spoken_response":"Today is April 19th, 2026, sir."}
"what's twelve times eight" → {"type":"chat","app":null,"action":null,"parameters":{},"spoken_response":"Ninety-six, sir."}
"good morning" → {"type":"chat","app":null,"action":null,"parameters":{},"spoken_response":"Good morning, sir."}

ACTION examples (one per category — generalise to similar phrasing):
"open spotify" → {"type":"action","app":"spotify","action":"open_app","parameters":{"target":"spotify"},"spoken_response":"Opening."}
"play lana del rey on spotify" → {"type":"action","app":"spotify","action":"play_spotify","parameters":{"target":"lana del rey"},"spoken_response":"Playing."}
"search neymar on youtube" → {"type":"action","app":"browser","action":"browser_search_youtube","parameters":{"query":"neymar"},"spoken_response":"Searching YouTube."}
"send hi to renan on discord" → {"type":"action","app":"discord","action":"discord_send_message","parameters":{"target_type":"dm","target_name":"renan","message":"Hi."},"spoken_response":"Done, sir."}
"open a new tab" → {"type":"action","app":"browser","action":"browser_new_tab","parameters":{},"spoken_response":"Done."}
"mute" → {"type":"action","app":null,"action":"volume_mute","parameters":{},"spoken_response":"Done."}
"take a screenshot" → {"type":"action","app":null,"action":"screenshot","parameters":{},"spoken_response":"Done."}
"open my downloads folder" → {"type":"action","app":null,"action":"open_folder","parameters":{"target":"downloads"},"spoken_response":"Opening Downloads, sir."}
"show off" → {"type":"action","app":null,"action":"show_off","parameters":{},"spoken_response":"Observe, sir."}"""


class LocalLLM(ILLM):
    """LLM driver with graceful fallback across services.

    Takes a primary service and an optional list of fallback services.
    On rate-limit or transport failure, walks down the fallback list
    until one succeeds. The fallback chain is built by the factory
    from whatever API keys the user has configured — e.g. Groq → Gemini
    → Anthropic — so hitting Groq's daily quota doesn't brick the
    assistant as long as the user has another provider set up.

    Spoken error messages route through the Strings catalogue so the
    user hears them in the language they've configured (en-US / pt-BR).
    """

    def __init__(
        self,
        service: LMStudioService,
        temperature: float = 0.1,
        history_turns: int = 6,
        fallback_services: list[object] | None = None,
        strings: "Strings | None" = None,
    ) -> None:
        self._primary_service = service
        self._fallback_services: list[object] = list(fallback_services or [])
        self._temperature = temperature
        self._history_turns = history_turns
        self._strings = strings
        # Track which service we should try first this turn — on a
        # rate-limit response we promote the fallback that actually
        # worked so the next turn doesn't pay the retry roundtrip.
        self._service: object = service

    def _services_in_order(self) -> list[object]:
        """Primary first, then any fallbacks we still trust."""
        chain = [self._service]
        for svc in [self._primary_service, *self._fallback_services]:
            if svc is not self._service and svc not in chain:
                chain.append(svc)
        return chain

    def _promote(self, service: object) -> None:
        if service is not self._service:
            LOGGER.info(
                "llm_failover_promoted",
                extra={
                    "event_data": {
                        "from": getattr(self._service, "model", "?"),
                        "to": getattr(service, "model", "?"),
                    }
                },
            )
            self._service = service

    def _error_text(self, key: str, default: str) -> str:
        if self._strings is None:
            return default
        try:
            return self._strings.get(key)
        except Exception:  # pragma: no cover
            return default

    def interpret(self, text: str) -> str:
        return self.decide(text).spoken_response

    def decide(self, text: str, history: Sequence[ChatTurn] | None = None) -> LLMDecision:
        messages = self._build_messages(text, history)

        total_chars_in = sum(len(m.content) for m in messages)
        log(
            Category.LLM,
            f"sending prompt to {self._service.model}: {text!r}",
            history_turns=_history_turn_count(messages),
            temperature=self._temperature,
            chars_in=total_chars_in,
        )

        # Walk the service chain until one succeeds. Rate-limit and
        # network errors promote us to the next provider; auth / bad-
        # request errors short-circuit (trying the same request on
        # another key would fail the same way).
        last_exc: Exception | None = None
        saw_rate_limit = False
        for service in self._services_in_order():
            try:
                with timed(
                    Category.LLM, "chat request", model=service.model
                ) as m:
                    raw = service.chat(
                        messages,
                        temperature=self._temperature,
                        max_tokens=120,
                    )
                    m["chars_in"] = total_chars_in
                    m["chars_out"] = len(raw)
            except LMStudioUnavailableError as exc:
                log(
                    Category.LLM,
                    f"{service.model} unavailable: {exc}",
                    level=logging.WARNING,
                )
                last_exc = exc
                continue
            except LMStudioError as exc:
                log(
                    Category.LLM,
                    f"{service.model} request failed: {exc}",
                    level=logging.WARNING,
                )
                last_exc = exc
                if self._is_rate_limit_error(exc):
                    saw_rate_limit = True
                    continue
                # Auth errors / 400s: don't try other providers, they
                # don't help. Still return the same error message.
                return LLMDecision(
                    type="chat",
                    spoken_response=self._error_text(
                        "llm_request_failed",
                        "I couldn't process that right now, sir.",
                    ),
                )
            # Success — remember which service to try first next turn.
            self._promote(service)
            break
        else:
            # Ran out of services without a successful response.
            if saw_rate_limit:
                return LLMDecision(
                    type="chat",
                    spoken_response=self._error_text(
                        "llm_rate_limited",
                        "I've reached the AI provider's daily quota, sir.",
                    ),
                )
            if isinstance(last_exc, LMStudioUnavailableError):
                return LLMDecision(
                    type="chat",
                    spoken_response=self._error_text(
                        "llm_unavailable", "LM Studio is not running, sir."
                    ),
                )
            return LLMDecision(
                type="chat",
                spoken_response=self._error_text(
                    "llm_request_failed",
                    "I couldn't process that right now, sir.",
                ),
            )

        log(Category.LLM, f"raw response: {raw.strip()!r}")

        with timed(Category.PARSER, "parse decision") as m:
            decision = parse_decision(raw)
            m["parsed"] = decision is not None
        if decision is None:
            log(Category.PARSER, "could not parse JSON from response", level=logging.WARNING)
            return LLMDecision(
                type="chat",
                spoken_response=self._error_text(
                    "llm_unintelligible", "I couldn't understand that, sir."
                ),
            )
        log(
            Category.PARSER,
            f"decision type={decision.type} action={decision.action}",
            app=decision.app,
            target=(decision.parameters or {}).get("target"),
            spoken=(decision.spoken_response or "")[:120],
        )
        return decision

    @staticmethod
    def _is_rate_limit_error(exc: Exception) -> bool:
        # LMStudioService raises LMStudioError("HTTP 429: ...") on quota
        # hits; AnthropicService follows the same convention. Matching
        # on the status code keeps us provider-agnostic.
        message = str(exc).lower()
        return "429" in message or "rate_limit" in message or "rate limit" in message

    def decide_streaming(
        self,
        text: str,
        history: Sequence[ChatTurn] | None = None,
    ) -> Iterator[StreamEvent]:
        """Stream the decision from LM Studio and yield progressive events.

        Event sequence (all optional, in order):
        - `ActionReady` once the action/parameters block has fully arrived.
        - Zero or more `SpokenChunk`s as `spoken_response` sentences close.
        - Exactly one terminal `ParseComplete` with the full LLMDecision,
          or `ParseComplete(decision=None)` if parsing failed.

        On LM Studio errors we yield a `ParseComplete` with a synthesised
        fallback decision so the caller doesn't need to handle exceptions
        mid-iteration — matches the ergonomics of `decide()`.
        """
        messages = self._build_messages(text, history)
        total_chars_in = sum(len(m.content) for m in messages)
        log(
            Category.LLM,
            f"streaming prompt to {self._service.model}: {text!r}",
            history_turns=_history_turn_count(messages),
            temperature=self._temperature,
            chars_in=total_chars_in,
        )

        # Try the chain until one provider streams successfully. The
        # delicate case is failing AFTER we've already yielded events
        # (e.g. the stream died mid-way) — in that case we keep what
        # the parser has and finalise, rather than switching
        # providers partway through a sentence. Pre-first-token
        # failures DO trigger failover.
        parser = StreamingDecisionParser()
        yielded_any = False
        last_exc: Exception | None = None
        saw_rate_limit = False

        for service in self._services_in_order():
            try:
                stream = service.chat_stream(
                    messages,
                    temperature=self._temperature,
                    max_tokens=120,
                )
                for delta in stream:
                    yielded_any = True
                    for event in parser.feed(delta):
                        yield event
                # Streamed fully — promote and break out.
                self._promote(service)
                break
            except LMStudioUnavailableError as exc:
                log(
                    Category.LLM,
                    f"{service.model} unavailable: {exc}",
                    level=logging.WARNING,
                )
                last_exc = exc
                if yielded_any:
                    break
                continue
            except LMStudioError as exc:
                log(
                    Category.LLM,
                    f"{service.model} stream failed: {exc}",
                    level=logging.WARNING,
                )
                last_exc = exc
                if self._is_rate_limit_error(exc):
                    saw_rate_limit = True
                    if not yielded_any:
                        continue
                if yielded_any:
                    break
                # Hard failure with no tokens yielded yet — try the
                # next provider (unless it was rate-limit, handled
                # above).
                if not self._is_rate_limit_error(exc):
                    # A 400 / 401 won't get better on the next
                    # provider — bail to the error branch below.
                    break

        if not yielded_any and last_exc is not None:
            # Every provider failed before emitting any tokens.
            if saw_rate_limit:
                spoken = self._error_text(
                    "llm_rate_limited",
                    "I've reached the AI provider's daily quota, sir.",
                )
            elif isinstance(last_exc, LMStudioUnavailableError):
                spoken = self._error_text(
                    "llm_unavailable", "LM Studio is not running, sir."
                )
            else:
                spoken = self._error_text(
                    "llm_request_failed",
                    "I couldn't process that right now, sir.",
                )
            yield ParseComplete(
                LLMDecision(type="chat", spoken_response=spoken)
            )
            return

        for event in parser.finalize():
            yield event
        log(
            Category.LLM,
            f"stream raw buffer: {parser.buffer.strip()!r}",
        )

    def _build_messages(
        self,
        text: str,
        history: Sequence[ChatTurn] | None,
    ) -> list[ChatMessage]:
        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=DECISION_SYSTEM_PROMPT)
        ]
        for turn in list(history or ())[-self._history_turns:]:
            if turn.role == "assistant":
                # Wrap prior assistant responses in the same JSON envelope
                # we expect back. Sending them as raw text teaches small
                # models that assistant turns are plain text and they stop
                # emitting JSON on the next reply — a drift we saw live
                # with Qwen 2.5 3B after one successful turn.
                #
                # Important: infer type=action vs type=chat from the
                # spoken_response. Pre-fix every assistant turn was wrapped
                # as type=chat even if the original turn was an action;
                # that poisoned the in-context learning and the model
                # started emitting type=chat+"Fechando." for commands like
                # "fecha o Spotify" because it saw historical chat turns
                # using action ack phrases.
                envelope = _envelope_for_assistant_turn(turn.content)
                messages.append(
                    ChatMessage(
                        role="assistant",
                        content=json.dumps(envelope, ensure_ascii=False),
                    )
                )
            else:
                messages.append(ChatMessage(role="user", content=turn.content))
        messages.append(ChatMessage(role="user", content=_build_user_message(text)))
        return messages


def _history_turn_count(messages: Sequence[ChatMessage]) -> int:
    # Exclude the system prompt and the latest user turn — we only want to
    # report how many prior turns of context were prepended.
    return max(0, len(messages) - 2)


# Canonical action ack phrases from DECISION_SYSTEM_PROMPT. If an
# assistant turn's spoken text matches one of these, the original turn
# was an action — wrap it as type=action in the history so the model
# sees consistent labelling instead of a pile of chat turns that happen
# to contain ack phrases.
_ACTION_ACK_PHRASES = frozenset(
    {
        # English (current default when JARVIS_LANGUAGE=en-US)
        "opening.",
        "opening the site.",
        "opening the link.",
        "closing.",
        "playing.",
        "searching.",
        "searching youtube.",
        "searching images.",
        "searching news.",
        "done.",
        "done, sir.",
        "observe, sir.",
        # Portuguese legacy (still emitted when LANGUAGE=pt-BR + Piper voice)
        "abrindo.",
        "abrindo o site.",
        "abrindo o link.",
        "fechando.",
        "tocando.",
        "pesquisando.",
        "buscando no youtube.",
        "buscando imagens.",
        "buscando notícias.",
        "pronto.",
        "feito.",
        "observe.",
    }
)


def _envelope_for_assistant_turn(spoken: str) -> dict:
    """Map a historical assistant spoken_response to the JSON envelope we
    sent the LLM. Action ack phrases get type=action; everything else
    stays chat. Keeping `action` null even for action-classified history
    is fine — the model only needs the type/spoken pairing to stop
    learning the wrong classification pattern, not the specific action
    (which rarely matters for the next turn's decision)."""
    normalised = spoken.strip().lower()
    envelope_type = "action" if normalised in _ACTION_ACK_PHRASES else "chat"
    return {
        "type": envelope_type,
        "app": None,
        "action": None,
        "parameters": {},
        "spoken_response": spoken,
    }


def _build_user_message(text: str, now: datetime | None = None) -> str:
    """Prepend current date/time so the model can answer time-sensitive questions
    without pulling them from its weights (which are stale)."""
    current = now or datetime.now()
    context = f"[Data atual: {current:%Y-%m-%d}. Hora atual: {current:%H:%M}.]"
    return f"{context}\n{text.strip()}"
