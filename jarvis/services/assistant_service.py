from __future__ import annotations

import logging
import re
import threading
import time

from jarvis.config.strings import Strings
from jarvis.enums.action_type import ActionType
from jarvis.interfaces.icommand_interpreter import ICommandInterpreter
from jarvis.interfaces.iaction_executor import IActionExecutor
from jarvis.interfaces.illm import ILLM
from jarvis.interfaces.itext_to_speech import ITextToSpeech
from jarvis.models.command import Command
from jarvis.models.interaction_result import InteractionResult
from jarvis.models.llm_decision import LLMDecision
from jarvis.services.conversation_memory import ConversationMemory
from jarvis.services.local_intent_handler import LocalIntentHandler
from jarvis.utils.command_mapper import CommandMapper


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
}

_DISCORD_LABEL_KEYS = ("target_name", "channel_name", "server_name", "site", "query", "sender", "subject", "url")

# Wake word: the assistant only reacts when it hears "jarvis" in the utterance.
# We accept a small whitelist of common STT mishears so phrases like
# "charges manda um oi..." still land. Adding a new alternative is intentional:
# it must be rare enough as a real word that false-positives stay low.
_WAKE_WORD_ALTS = (
    r"jarvis|jards|jardins|jarbas|jarves|jarvez|jarviz|jarviso|jarbis|"
    r"charges|chavis|charbs|jervis|jarveis"
)
_WAKE_WORD_RE = re.compile(rf"\b({_WAKE_WORD_ALTS})\b", re.IGNORECASE)
# Only strips the FIRST occurrence so embedded mentions
# ("... e fala que foi o Jarvis que mandou") stay intact.
_WAKE_WORD_STRIP_RE = re.compile(rf"\b({_WAKE_WORD_ALTS})\b[\s,.!?:;]*", re.IGNORECASE)

LOGGER = logging.getLogger(__name__)


class AssistantService:
    def __init__(
        self,
        strings: Strings,
        local_intent_handler: LocalIntentHandler,
        command_interpreter: ICommandInterpreter,
        action_executor: IActionExecutor,
        llm: ILLM,
        text_to_speech: ITextToSpeech,
        command_mapper: CommandMapper,
        conversation_memory: ConversationMemory | None = None,
    ) -> None:
        self._strings = strings
        self._local_intent_handler = local_intent_handler
        self._command_interpreter = command_interpreter
        self._action_executor = action_executor
        self._llm = llm
        self._text_to_speech = text_to_speech
        self._command_mapper = command_mapper
        self._memory = conversation_memory or ConversationMemory()
        self._speech_thread: threading.Thread | None = None

    def set_llm(self, llm: ILLM) -> None:
        self._llm = llm

    def handle(self, text: str) -> str:
        return self.process(text).spoken_response

    def process(self, text: str) -> InteractionResult:
        cleaned_text = text.strip()
        if not cleaned_text:
            response = self._strings.get("empty_transcript")
            self._speak(response)
            return InteractionResult(transcript=text, command=None, action_result=None, spoken_response=response)

        if not _WAKE_WORD_RE.search(self._strip_accents(cleaned_text)):
            LOGGER.info(
                "wake_word_missing",
                extra={"event_data": {"transcript": cleaned_text[:120]}},
            )
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
            self._speak(response)
            self._log_response("bare_wake_word", response)
            return InteractionResult(transcript=text, command=None, action_result=None, spoken_response=response)

        if self._llm.is_fallback:
            local_response = self._local_intent_handler.handle(cleaned_text)
            if local_response is not None:
                self._speak(local_response)
                self._log_response("fallback_local", local_response)
                return InteractionResult(transcript=cleaned_text, command=None, action_result=None, spoken_response=local_response)

        self._memory.add_user(cleaned_text)

        command_payload = self._command_interpreter.interpret(cleaned_text)
        if command_payload is not None:
            command = self._command_mapper.from_payload(command_payload)
            ack = self._build_ack(command)
            # Speak the ack in parallel with the action execution: Piper takes
            # ~2-3s and Discord/Spotify automation takes ~1-2s, so running them
            # sequentially doubles the perceived latency. TTS uses the audio
            # output; automation uses keyboard focus — they don't compete.
            self._speak_async(ack)
            t2 = time.perf_counter()
            action_result = self._action_executor.execute(command)
            LOGGER.info(
                "action_executed",
                extra={
                    "event_data": {
                        "execute_ms": int((time.perf_counter() - t2) * 1000),
                        "success": action_result.success,
                        "action": action_result.action.value,
                        "target": action_result.target,
                        "message": action_result.message,
                    }
                },
            )
            if action_result.success:
                response = ack
            else:
                response = self._strings.get("command_not_found")
                self._speak(response)
            self._memory.add_assistant(response)
            self._log_response(
                "rule_based",
                response,
                action=command.action.value,
                success=action_result.success,
            )
            return InteractionResult(
                transcript=cleaned_text,
                command=command,
                action_result=action_result,
                spoken_response=response,
            )

        t3 = time.perf_counter()
        decision = self._llm.decide(cleaned_text, history=self._memory.snapshot()[:-1])
        LOGGER.info(
            "llm_done",
            extra={
                "event_data": {
                    "llm_ms": int((time.perf_counter() - t3) * 1000),
                    "type": decision.type,
                    "is_fallback": self._llm.is_fallback,
                    "action": decision.action,
                    "spoken_preview": (decision.spoken_response or "")[:200],
                }
            },
        )

        if decision.is_action:
            command = self._command_from_decision(decision)
            if command is not None:
                ack = decision.spoken_response or self._build_ack(command)
                self._speak_async(ack)
                t4 = time.perf_counter()
                action_result = self._action_executor.execute(command)
                LOGGER.info(
                    "action_executed",
                    extra={
                        "event_data": {
                            "source": "llm",
                            "execute_ms": int((time.perf_counter() - t4) * 1000),
                            "success": action_result.success,
                            "action": action_result.action.value,
                            "target": action_result.target,
                            "message": action_result.message,
                        }
                    },
                )
                if action_result.success:
                    response = ack
                else:
                    response = self._strings.get("command_not_found")
                    self._speak(response)
                self._memory.add_assistant(response)
                self._log_response(
                    "llm_action",
                    response,
                    action=command.action.value,
                    success=action_result.success,
                )
                return InteractionResult(
                    transcript=cleaned_text,
                    command=command,
                    action_result=action_result,
                    spoken_response=response,
                )

        response = decision.spoken_response.strip() or self._strings.get("no_response")
        self._speak(response)
        self._memory.add_assistant(response)
        self._log_response("llm_chat", response, is_fallback=self._llm.is_fallback)
        return InteractionResult(transcript=cleaned_text, command=None, action_result=None, spoken_response=response)

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

    def _speak(self, text: str) -> None:
        """Synchronous speak. Waits for any in-flight async speech first."""
        self._wait_for_speech()
        t = time.perf_counter()
        self._text_to_speech.speak(text)
        LOGGER.info(
            "tts_spoken",
            extra={
                "event_data": {
                    "tts_ms": int((time.perf_counter() - t) * 1000),
                    "chars": len(text),
                    "mode": "sync",
                }
            },
        )

    def _speak_async(self, text: str) -> None:
        """Fire-and-forget speak. Used to parallelize the ack with action execution.

        Ensures we never speak over ourselves by joining the previous thread
        before starting a new one.
        """
        self._wait_for_speech()
        t = time.perf_counter()

        def _run() -> None:
            try:
                self._text_to_speech.speak(text)
            finally:
                LOGGER.info(
                    "tts_spoken",
                    extra={
                        "event_data": {
                            "tts_ms": int((time.perf_counter() - t) * 1000),
                            "chars": len(text),
                            "mode": "async",
                        }
                    },
                )

        self._speech_thread = threading.Thread(target=_run, daemon=True)
        self._speech_thread.start()

    def _wait_for_speech(self) -> None:
        thread = self._speech_thread
        if thread is not None and thread.is_alive():
            thread.join()
        self._speech_thread = None

    def _log_response(self, source: str, response: str, **extra: object) -> None:
        """Log what Jarvis is saying back so the assistant's behavior is debuggable.

        ``source`` is the path that produced it: 'wake_gate', 'greeting',
        'fallback_local', 'rule_based', 'llm_action', 'llm_chat', etc.
        """
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
