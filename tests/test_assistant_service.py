from __future__ import annotations

from datetime import datetime

from jarvis.enums.action_type import ActionType
from jarvis.interfaces.iaction_executor import IActionExecutor
from jarvis.models.action_result import ActionResult
from jarvis.models.command import Command
from jarvis.services.assistant_service import AssistantService
from jarvis.services.local_intent_handler import LocalIntentHandler
from jarvis.utils.command_mapper import CommandMapper


class FakeLLM:
    def __init__(self, response: str) -> None:
        self._response = response
        self.calls: list[str] = []

    def interpret(self, text: str) -> str:
        self.calls.append(text)
        return self._response


class FakeTextToSpeech:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def speak(self, text: str) -> None:
        self.messages.append(text)


class FakeAudioFeedback:
    def __init__(self) -> None:
        self.success_calls = 0

    def play_success_response(self) -> None:
        self.success_calls += 1


class FakeCommandInterpreter:
    def __init__(self, payload: dict[str, str] | None) -> None:
        self._payload = payload

    def interpret(self, text: str) -> dict[str, str] | None:
        return self._payload


class FakeActionExecutor(IActionExecutor):
    def __init__(self, result: ActionResult) -> None:
        self._result = result

    def execute(self, command: Command) -> ActionResult:
        return self._result


def test_assistant_service_answers_local_date_query() -> None:
    tts = FakeTextToSpeech()
    service = AssistantService(
        local_intent_handler=LocalIntentHandler(now_provider=lambda: datetime(2026, 4, 14, 15, 45)),
        command_interpreter=FakeCommandInterpreter(None),
        action_executor=FakeActionExecutor(ActionResult(True, "Opened.", ActionType.OPEN_APP, "discord")),
        llm=FakeLLM("ignored"),
        text_to_speech=tts,
        audio_feedback=FakeAudioFeedback(),
        command_mapper=CommandMapper(),
    )

    response = service.handle("What day is today?")

    assert response == "Today is April 14, 2026, sir."
    assert tts.messages == ["Today is April 14, 2026, sir."]


def test_assistant_service_answers_local_weather_query() -> None:
    tts = FakeTextToSpeech()
    service = AssistantService(
        local_intent_handler=LocalIntentHandler(),
        command_interpreter=FakeCommandInterpreter(None),
        action_executor=FakeActionExecutor(ActionResult(True, "Opened.", ActionType.OPEN_APP, "discord")),
        llm=FakeLLM("ignored"),
        text_to_speech=tts,
        audio_feedback=FakeAudioFeedback(),
        command_mapper=CommandMapper(),
    )

    response = service.handle("Will it rain today?")

    assert response == "I cannot check weather without internet access, sir."
    assert tts.messages == ["I cannot check weather without internet access, sir."]


def test_assistant_service_uses_llm_for_non_local_question() -> None:
    llm = FakeLLM("Python is a programming language, sir.")
    tts = FakeTextToSpeech()
    service = AssistantService(
        local_intent_handler=LocalIntentHandler(),
        command_interpreter=FakeCommandInterpreter(None),
        action_executor=FakeActionExecutor(ActionResult(True, "Opened.", ActionType.OPEN_APP, "discord")),
        llm=llm,
        text_to_speech=tts,
        audio_feedback=FakeAudioFeedback(),
        command_mapper=CommandMapper(),
    )

    response = service.handle("Explain what Python is")

    assert response == "Python is a programming language, sir."
    assert llm.calls == ["Explain what Python is"]
    assert tts.messages == ["Python is a programming language, sir."]


def test_assistant_service_preserves_success_audio_for_commands() -> None:
    audio_feedback = FakeAudioFeedback()
    service = AssistantService(
        local_intent_handler=LocalIntentHandler(),
        command_interpreter=FakeCommandInterpreter({"action": ActionType.OPEN_APP.value, "target": "discord"}),
        action_executor=FakeActionExecutor(ActionResult(True, "Opened discord.", ActionType.OPEN_APP, "discord")),
        llm=FakeLLM("ignored"),
        text_to_speech=FakeTextToSpeech(),
        audio_feedback=audio_feedback,
        command_mapper=CommandMapper(),
    )

    result = service.process("Jarvis, open Discord")

    assert result.action_result is not None
    assert result.action_result.success is True
    assert audio_feedback.success_calls == 1


def test_assistant_service_does_not_trigger_success_audio_for_failed_command() -> None:
    audio_feedback = FakeAudioFeedback()
    service = AssistantService(
        local_intent_handler=LocalIntentHandler(),
        command_interpreter=FakeCommandInterpreter({"action": ActionType.OPEN_APP.value, "target": "unknown"}),
        action_executor=FakeActionExecutor(
            ActionResult(False, "Application 'unknown' was not found.", ActionType.OPEN_APP, "unknown")
        ),
        llm=FakeLLM("ignored"),
        text_to_speech=FakeTextToSpeech(),
        audio_feedback=audio_feedback,
        command_mapper=CommandMapper(),
    )

    result = service.process("Jarvis, open unknown")

    assert result.action_result is not None
    assert result.action_result.success is False
    assert audio_feedback.success_calls == 0
