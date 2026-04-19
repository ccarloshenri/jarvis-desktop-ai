from __future__ import annotations

import dataclasses
import logging
import re

from jarvis.config.strings import Strings
from jarvis.enums.action_type import ActionType
from jarvis.interfaces.iaction_executor import IActionExecutor
from jarvis.interfaces.illm import ILLM
from jarvis.interfaces.itext_to_speech import ITextToSpeech
from jarvis.models.command import Command
from jarvis.models.interaction_result import InteractionResult
from jarvis.models.llm_decision import LLMDecision
from jarvis.models.pending_confirmation import PendingConfirmation
from jarvis.services.context_aware_correction_service import (
    ContextAwareCorrectionService,
    CorrectionOutcome,
)
from jarvis.services.conversation_memory import ConversationMemory
from jarvis.utils.command_mapper import CommandMapper
from jarvis.utils.llm_response_parser import (
    ActionReady,
    ParseComplete,
    SpokenChunk,
)
from jarvis.utils.performance import Category, log, timed
from jarvis.utils.yes_no_classifier import YesNoAnswer, classify as classify_yes_no


_ACK_KEYS = {
    ActionType.OPEN_APP: "ack_open_app",
    ActionType.CLOSE_APP: "ack_close_app",
    ActionType.PLAY_SPOTIFY: "ack_play_spotify",
    ActionType.SEARCH_WEB: "ack_search_web",
    ActionType.DISCORD_OPEN: "ack_discord_open",
    ActionType.DISCORD_CLOSE: "ack_discord_close",
    ActionType.DISCORD_FOCUS: "ack_discord_focus",
    ActionType.DISCORD_OPEN_DM: "ack_discord_open_dm",
    ActionType.DISCORD_OPEN_SERVER: "ack_discord_open_server",
    ActionType.DISCORD_OPEN_CHANNEL: "ack_discord_open_channel",
    ActionType.DISCORD_SEND_MESSAGE: "ack_discord_send_message",
    ActionType.DISCORD_REPLY_CURRENT: "ack_discord_reply_current",
    ActionType.DISCORD_TOGGLE_MUTE: "ack_discord_toggle_mute",
    ActionType.DISCORD_TOGGLE_DEAFEN: "ack_discord_toggle_deafen",
    ActionType.DISCORD_JOIN_VOICE: "ack_discord_join_voice",
    ActionType.DISCORD_LEAVE_VOICE: "ack_discord_leave_voice",
    ActionType.DISCORD_SET_STATUS: "ack_discord_set_status",
    ActionType.DISCORD_PREVIOUS: "ack_discord_previous",
    ActionType.BROWSER_OPEN: "ack_browser_open",
    ActionType.BROWSER_CLOSE: "ack_browser_close",
    ActionType.BROWSER_FOCUS: "ack_browser_focus",
    ActionType.BROWSER_OPEN_SITE: "ack_browser_open_site",
    ActionType.BROWSER_OPEN_URL: "ack_browser_open_url",
    ActionType.BROWSER_SEARCH_GOOGLE: "ack_browser_search_google",
    ActionType.BROWSER_SEARCH_YOUTUBE: "ack_browser_search_youtube",
    ActionType.BROWSER_SEARCH_IMAGES: "ack_browser_search_images",
    ActionType.BROWSER_SEARCH_NEWS: "ack_browser_search_news",
    ActionType.BROWSER_NEW_TAB: "ack_browser_new_tab",
    ActionType.BROWSER_CLOSE_TAB: "ack_browser_close_tab",
    ActionType.BROWSER_NEXT_TAB: "ack_browser_next_tab",
    ActionType.BROWSER_PREV_TAB: "ack_browser_prev_tab",
    ActionType.BROWSER_BACK: "ack_browser_back",
    ActionType.BROWSER_FORWARD: "ack_browser_forward",
    ActionType.BROWSER_RELOAD: "ack_browser_reload",
    ActionType.BROWSER_OPEN_EMAIL: "ack_browser_open_email",
    ActionType.BROWSER_CHECK_UNREAD: "ack_browser_check_unread",
    ActionType.BROWSER_SEARCH_EMAIL_FROM: "ack_browser_search_email_from",
    ActionType.BROWSER_SEARCH_EMAIL_SUBJECT: "ack_browser_search_email_subject",
    ActionType.SHOW_OFF: "ack_show_off",
    ActionType.VOLUME_UP: "ack_volume_up",
    ActionType.VOLUME_DOWN: "ack_volume_down",
    ActionType.VOLUME_MUTE: "ack_volume_mute",
    ActionType.SCREENSHOT: "ack_screenshot",
    ActionType.CLIPBOARD_READ: "ack_clipboard_read",
    ActionType.LOCK_SCREEN: "ack_lock_screen",
    ActionType.OPEN_FOLDER: "ack_open_folder",
}

_DISCORD_LABEL_KEYS = ("target_name", "channel_name", "server_name", "site", "query", "sender", "subject", "url")

# Wake-word gate: we filter *before* hitting the LLM. Routing every random
# chatter in the room through a local model would waste CPU/GPU cycles and
# tighten the wake-word intent of the product. The alternatives cover the
# most common STT mishears of "Jarvis" — adding more must stay rare enough
# as real words to keep false positives low.
_WAKE_WORD_ALTS = (
    r"jarvis|jards|jardins|jarbas|jarves|jarvez|jarviz|jarviso|jarbis|"
    r"charges|chavis|charbs|jervis|jarveis"
)
_WAKE_WORD_RE = re.compile(rf"\b({_WAKE_WORD_ALTS})\b", re.IGNORECASE)
_WAKE_WORD_STRIP_RE = re.compile(rf"\b({_WAKE_WORD_ALTS})\b[\s,.!?:;]*", re.IGNORECASE)

LOGGER = logging.getLogger(__name__)


class AssistantService:
    """Single pipeline: wake-word gate -> LLM -> execute-or-speak.

    Every interpretation decision lives in the LLM (LocalLLM over LM Studio).
    No rule-based shortcut layer, no keyword fallback — if the LLM fails,
    we speak a generic error rather than attempt a hand-rolled intent match.
    """

    def __init__(
        self,
        strings: Strings,
        action_executor: IActionExecutor,
        llm: ILLM,
        text_to_speech: ITextToSpeech,
        command_mapper: CommandMapper,
        conversation_memory: ConversationMemory | None = None,
        correction_service: ContextAwareCorrectionService | None = None,
        llm_streaming: bool = True,
    ) -> None:
        self._strings = strings
        self._action_executor = action_executor
        self._llm = llm
        self._text_to_speech = text_to_speech
        self._command_mapper = command_mapper
        self._memory = conversation_memory or ConversationMemory()
        self._correction_service = correction_service
        # Holds a medium-confidence correction between turns. When set, the
        # next utterance is interpreted as a yes/no answer to the question
        # we spoke; on UNKNOWN we drop it and fall through to the usual
        # wake-word + LLM flow. Optional (None) means no pending turn.
        self._pending_confirmation: PendingConfirmation | None = None
        # Stream only when the LLM impl supports it. Hard-check at init so
        # we fall back transparently for LLM stubs used in tests.
        self._llm_streaming = llm_streaming and hasattr(llm, "decide_streaming")

    def set_spotify_controller(self, controller: object) -> None:
        if hasattr(self._action_executor, "set_spotify_controller"):
            self._action_executor.set_spotify_controller(controller)  # type: ignore[attr-defined]

    def handle(self, text: str) -> str:
        return self.process(text).spoken_response

    def process(self, text: str) -> InteractionResult:
        cleaned_text = text.strip()
        if not cleaned_text:
            response = self._strings.get("empty_transcript")
            self._text_to_speech.speak(response)
            return InteractionResult(transcript=text, command=None, action_result=None, spoken_response=response)

        # If we asked a yes/no question last turn, try to resolve it here
        # *before* the wake-word gate. Users rarely re-invoke "Jarvis" just
        # to say "sim" — making confirmation require wake word would make
        # the UX feel hostile.
        if self._pending_confirmation is not None:
            handled = self._try_handle_confirmation(cleaned_text)
            if handled is not None:
                return handled

        if not _WAKE_WORD_RE.search(self._strip_accents(cleaned_text)):
            log(Category.SYSTEM, "wake word missing — ignoring", transcript=cleaned_text[:120])
            self._log_response("wake_gate", "")
            return InteractionResult(
                transcript=cleaned_text,
                command=None,
                action_result=None,
                spoken_response="",
            )

        cleaned_text = self._strip_wake_word(cleaned_text)
        if not cleaned_text:
            response = self._strings.get("greeting")
            self._text_to_speech.speak(response)
            self._log_response("bare_wake_word", response)
            return InteractionResult(transcript=text, command=None, action_result=None, spoken_response=response)

        self._memory.add_user(cleaned_text)

        decision, already_spoken = self._decide(cleaned_text)

        if decision.is_action:
            command = self._command_from_decision(decision)
            if command is not None:
                return self._handle_action_command(
                    command, decision.spoken_response, cleaned_text
                )

        response = decision.spoken_response.strip() or self._strings.get("no_response")
        if not already_spoken:
            self._text_to_speech.speak(response)
        self._memory.add_assistant(response)
        self._log_response("llm_chat", response)
        return InteractionResult(transcript=cleaned_text, command=None, action_result=None, spoken_response=response)

    def _decide(self, cleaned_text: str) -> tuple[LLMDecision, bool]:
        """Run the LLM and return (decision, already_spoken).

        `already_spoken` is True when streaming has already pushed the
        full spoken_response through the TTS pipeline; the caller must
        NOT speak it again (double audio). Streaming is only actually
        used for chat decisions — action acknowledgements are short and
        typically cache-hit, and we need them gated by the correction
        service before speaking, so streaming them is counterproductive.
        """
        history = self._memory.snapshot()[:-1]
        if not self._llm_streaming:
            with timed(Category.LLM, "decide") as m:
                decision = self._llm.decide(cleaned_text, history=history)
                m["type"] = decision.type
                m["action"] = decision.action
                m["spoken_preview"] = (decision.spoken_response or "")[:120]
            return decision, False

        buffered_spoken: list[str] = []
        streamed_to_tts = False
        action_detected = False
        decision: LLMDecision | None = None

        with timed(Category.LLM, "decide_streaming") as m:
            try:
                for event in self._llm.decide_streaming(  # type: ignore[attr-defined]
                    cleaned_text, history=history
                ):
                    if isinstance(event, ActionReady):
                        action_detected = True
                    elif isinstance(event, SpokenChunk):
                        if action_detected:
                            # Action flow: buffer the spoken chunks — the
                            # correction service may change the ack we
                            # actually speak, so committing them to the
                            # TTS pipeline early would be wrong.
                            buffered_spoken.append(event.text)
                        else:
                            self._text_to_speech.speak_stream_chunk(event.text)
                            streamed_to_tts = True
                    elif isinstance(event, ParseComplete):
                        decision = event.decision
            finally:
                if streamed_to_tts:
                    self._text_to_speech.speak_stream_end()
            m["type"] = (decision.type if decision else "unknown")
            m["action"] = decision.action if decision else None
            m["streamed"] = streamed_to_tts

        if decision is None:
            # Parser couldn't salvage a decision — same fallback as the
            # non-streaming path, routed through speak() since nothing
            # was streamed yet.
            decision = LLMDecision(
                type="chat",
                spoken_response=self._strings.get("no_response"),
            )
            return decision, streamed_to_tts

        # For action decisions, the buffered chunks reconstruct the full
        # spoken_response that the caller will pass through the correction
        # service. parse_decision already set decision.spoken_response
        # from the completed JSON, so buffered_spoken is a redundant
        # safety net — use it only if the parser somehow lost the field.
        if action_detected and not decision.spoken_response and buffered_spoken:
            decision = dataclasses.replace(
                decision, spoken_response=" ".join(buffered_spoken).strip()
            )
        return decision, streamed_to_tts

    def _handle_action_command(
        self, command: Command, llm_spoken: str, transcript: str
    ) -> InteractionResult:
        """Run context-aware correction, handle the three outcomes."""
        if self._correction_service is not None:
            result = self._correction_service.correct(command)
            if (
                result.outcome == CorrectionOutcome.NEEDS_CONFIRMATION
                and result.candidate_command is not None
                and result.resolution is not None
            ):
                spoken_candidate = result.resolution.spoken
                question = self._strings.get("confirm_candidate", candidate=spoken_candidate)
                self._text_to_speech.speak(question)
                self._pending_confirmation = PendingConfirmation(
                    candidate_command=result.candidate_command,
                    spoken_candidate=spoken_candidate,
                    original_target=result.resolution.original,
                )
                self._memory.add_assistant(question)
                self._log_response("correction_confirm", question, candidate=spoken_candidate)
                return InteractionResult(
                    transcript=transcript,
                    command=None,
                    action_result=None,
                    spoken_response=question,
                )
            command = result.command
        return self._execute_command(command, llm_spoken, transcript)

    def _execute_command(
        self, command: Command, llm_spoken: str, transcript: str
    ) -> InteractionResult:
        # Always use the localised ack phrase for actions — the LLM's
        # `spoken_response` was useful when the prompt and TTS were both
        # pt-BR, but with Groq TTS (English only) that Portuguese ack
        # gets spoken by an English voice and sounds absurd. The Strings
        # catalogue carries a proper per-language template with target
        # interpolation ("Opening Spotify, sir." / "Abrindo Spotify,
        # senhor."), so we just ignore llm_spoken here.
        del llm_spoken
        ack = self._build_ack(command)
        self._text_to_speech.speak(ack)
        log(
            Category.EXECUTOR,
            f"executing action: {command.action.value}",
            target=command.target,
        )
        with timed(Category.EXECUTOR, "execute", action=command.action.value) as m:
            action_result = self._action_executor.execute(command)
            m["success"] = action_result.success
            m["target"] = action_result.target
        if action_result.success:
            response = ack
        else:
            response = self._strings.get("command_not_found")
            self._text_to_speech.speak(response)
        self._memory.add_assistant(response)
        self._log_response(
            "llm_action",
            response,
            action=command.action.value,
            success=action_result.success,
        )
        return InteractionResult(
            transcript=transcript,
            command=command,
            action_result=action_result,
            spoken_response=response,
        )

    def _try_handle_confirmation(self, text: str) -> InteractionResult | None:
        """Consume the pending confirmation if the utterance reads as yes/no.

        Returns an InteractionResult when the confirmation is resolved
        (either direction); returns None if the utterance isn't a yes/no,
        in which case the caller should drop the pending state and run
        the utterance through the normal pipeline.
        """
        pending = self._pending_confirmation
        if pending is None:
            return None
        # Strip the wake word defensively — users sometimes prepend
        # "Jarvis, sim" even when it's not required.
        stripped = self._strip_wake_word(text).strip() or text
        answer = classify_yes_no(stripped)
        log(
            Category.SYSTEM,
            f"confirmation reply: {stripped!r} -> {answer.value}",
            candidate=pending.spoken_candidate,
        )
        if answer == YesNoAnswer.YES:
            self._pending_confirmation = None
            return self._execute_command(
                pending.candidate_command,
                self._build_ack(pending.candidate_command),
                stripped,
            )
        if answer == YesNoAnswer.NO:
            self._pending_confirmation = None
            response = self._strings.get("confirmation_cancelled")
            self._text_to_speech.speak(response)
            self._memory.add_assistant(response)
            self._log_response("confirmation_cancelled", response)
            return InteractionResult(
                transcript=stripped,
                command=None,
                action_result=None,
                spoken_response=response,
            )
        # UNKNOWN — drop the pending and let the caller reprocess as a
        # brand-new command. No cancellation message: if the user said
        # something unrelated, we don't want to interrupt them.
        self._pending_confirmation = None
        log(Category.SYSTEM, "confirmation dropped (unknown reply)")
        return None

    def _command_from_decision(self, decision: LLMDecision) -> Command | None:
        if not decision.action:
            return None
        params = dict(decision.parameters or {})
        target = ""
        raw_target = (
            params.get("target")
            or params.get("query")
            or params.get("app_name")
            or params.get("name")
        )
        if isinstance(raw_target, str):
            target = raw_target.strip()
        if not target and decision.app and not decision.action.startswith("discord_"):
            target = decision.app.strip()
        try:
            return self._command_mapper.from_payload(
                {"action": decision.action, "target": target, "parameters": params}
            )
        except (ValueError, KeyError) as exc:
            LOGGER.warning(
                "llm_decision_map_failed",
                extra={"event_data": {"error": str(exc), "action": decision.action, "target": target}},
            )
            return None

    def _build_ack(self, command: Command) -> str:
        key = _ACK_KEYS.get(command.action)
        if key is None:
            return self._strings.get("command_ok")
        label = command.target or self._discord_label(command) or ""
        return self._strings.get(key, target=command.target, label=label)

    def _discord_label(self, command: Command) -> str:
        params = command.parameters or {}
        for key in _DISCORD_LABEL_KEYS:
            value = params.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _log_response(self, source: str, response: str, **extra: object) -> None:
        payload: dict[str, object] = {"source": source, "response": response[:300]}
        payload.update(extra)
        LOGGER.info("jarvis_response", extra={"event_data": payload})

    def _strip_wake_word(self, text: str) -> str:
        cleaned = _WAKE_WORD_STRIP_RE.sub(" ", text, count=1)
        return re.sub(r"\s+", " ", cleaned).strip()

    def _strip_accents(self, text: str) -> str:
        return text.translate(
            str.maketrans("áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ",
                          "aaaaaeeeeiiiiooooouuuucAAAAAEEEEIIIIOOOOOUUUUC")
        )
