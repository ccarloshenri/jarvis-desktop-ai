from __future__ import annotations

import logging
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
from jarvis.services.local_intent_handler import LocalIntentHandler
from jarvis.utils.command_mapper import CommandMapper


_ACK_KEYS = {
    ActionType.OPEN_APP: "ack_open_app",
    ActionType.CLOSE_APP: "ack_close_app",
    ActionType.PLAY_SPOTIFY: "ack_play_spotify",
    ActionType.SEARCH_WEB: "ack_search_web",
}

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
    ) -> None:
        self._strings = strings
        self._local_intent_handler = local_intent_handler
        self._command_interpreter = command_interpreter
        self._action_executor = action_executor
        self._llm = llm
        self._text_to_speech = text_to_speech
        self._command_mapper = command_mapper

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

        if self._llm.is_fallback:
            local_response = self._local_intent_handler.handle(cleaned_text)
            if local_response is not None:
                self._speak(local_response)
                return InteractionResult(transcript=cleaned_text, command=None, action_result=None, spoken_response=local_response)

        command_payload = self._command_interpreter.interpret(cleaned_text)
        if command_payload is not None:
            command = self._command_mapper.from_payload(command_payload)
            ack = self._build_ack(command)
            self._speak(ack)
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
            return InteractionResult(
                transcript=cleaned_text,
                command=command,
                action_result=action_result,
                spoken_response=response,
            )

        t3 = time.perf_counter()
        decision = self._llm.decide(cleaned_text)
        LOGGER.info(
            "llm_done",
            extra={"event_data": {"llm_ms": int((time.perf_counter() - t3) * 1000), "type": decision.type}},
        )

        if decision.is_action:
            command = self._command_from_decision(decision)
            if command is not None:
                ack = decision.spoken_response or self._build_ack(command)
                self._speak(ack)
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
                return InteractionResult(
                    transcript=cleaned_text,
                    command=command,
                    action_result=action_result,
                    spoken_response=response,
                )

        response = decision.spoken_response.strip() or self._strings.get("no_response")
        self._speak(response)
        return InteractionResult(transcript=cleaned_text, command=None, action_result=None, spoken_response=response)

    def _command_from_decision(self, decision: LLMDecision) -> Command | None:
        if not decision.action:
            return None
        target = ""
        params = decision.parameters or {}
        if isinstance(params, dict):
            raw_target = params.get("target") or params.get("query") or params.get("app_name") or params.get("name")
            if isinstance(raw_target, str):
                target = raw_target.strip()
        if not target and decision.app:
            target = decision.app.strip()
        if not target:
            return None
        try:
            return self._command_mapper.from_payload({"action": decision.action, "target": target})
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
        return self._strings.get(key, target=command.target)

    def _speak(self, text: str) -> None:
        self._text_to_speech.speak(text)
