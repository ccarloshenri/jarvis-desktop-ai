from __future__ import annotations

import logging

from jarvis.config.strings import Strings
from jarvis.interfaces.icommand_interpreter import ICommandInterpreter
from jarvis.interfaces.iaction_executor import IActionExecutor
from jarvis.interfaces.illm import ILLM
from jarvis.interfaces.itext_to_speech import ITextToSpeech
from jarvis.models.interaction_result import InteractionResult
from jarvis.services.local_intent_handler import LocalIntentHandler
from jarvis.utils.command_mapper import CommandMapper

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

    def handle(self, text: str) -> str:
        return self.process(text).spoken_response

    def process(self, text: str) -> InteractionResult:
        cleaned_text = text.strip()
        if not cleaned_text:
            response = self._strings.get("empty_transcript")
            self._text_to_speech.speak(response)
            return InteractionResult(transcript=text, command=None, action_result=None, spoken_response=response)

        LOGGER.info("assistant_input", extra={"event_data": {"transcript": cleaned_text}})

        local_response = self._local_intent_handler.handle(cleaned_text)
        if local_response is not None:
            self._text_to_speech.speak(local_response)
            return InteractionResult(transcript=cleaned_text, command=None, action_result=None, spoken_response=local_response)

        command_payload = self._command_interpreter.interpret(cleaned_text)
        if command_payload is not None:
            command = self._command_mapper.from_payload(command_payload)
            action_result = self._action_executor.execute(command)
            response = self._strings.get("command_ok") if action_result.success else self._strings.get("command_not_found")
            self._text_to_speech.speak(response)
            LOGGER.info(
                "assistant_command_result",
                extra={
                    "event_data": {
                        "success": action_result.success,
                        "message": action_result.message,
                        "action": action_result.action.value,
                        "target": action_result.target,
                    }
                },
            )
            return InteractionResult(
                transcript=cleaned_text,
                command=command,
                action_result=action_result,
                spoken_response=response,
            )

        response = self._llm.interpret(cleaned_text).strip() or self._strings.get("no_response")
        self._text_to_speech.speak(response)
        return InteractionResult(transcript=cleaned_text, command=None, action_result=None, spoken_response=response)
