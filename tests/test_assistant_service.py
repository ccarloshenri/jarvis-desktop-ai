from __future__ import annotations

from datetime import datetime

from jarvis.config.strings import Strings
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


STRINGS_PT = Strings("pt-BR")


def _build_service(
    *,
    local_intent_handler: LocalIntentHandler | None = None,
    command_interpreter: FakeCommandInterpreter | None = None,
    action_executor: FakeActionExecutor | None = None,
    llm: FakeLLM | None = None,
    tts: FakeTextToSpeech | None = None,
) -> AssistantService:
    return AssistantService(
        strings=STRINGS_PT,
        local_intent_handler=local_intent_handler or LocalIntentHandler(strings=STRINGS_PT),
        command_interpreter=command_interpreter or FakeCommandInterpreter(None),
        action_executor=action_executor
        or FakeActionExecutor(ActionResult(True, "Opened.", ActionType.OPEN_APP, "discord")),
        llm=llm or FakeLLM("ignored"),
        text_to_speech=tts or FakeTextToSpeech(),
        command_mapper=CommandMapper(),
    )


def test_assistant_service_answers_local_date_query() -> None:
    tts = FakeTextToSpeech()
    service = _build_service(
        local_intent_handler=LocalIntentHandler(
            strings=STRINGS_PT, now_provider=lambda: datetime(2026, 4, 14, 15, 45)
        ),
        tts=tts,
    )

    response = service.handle("Que dia é hoje?")

    expected = "Hoje é 14 de abril de 2026, senhor."
    assert response == expected
    assert tts.messages == [expected]


def test_assistant_service_answers_local_weather_query() -> None:
    tts = FakeTextToSpeech()
    service = _build_service(tts=tts)

    response = service.handle("Vai chover hoje?")

    expected = STRINGS_PT.get("weather_unavailable")
    assert response == expected
    assert tts.messages == [expected]


def test_assistant_service_uses_llm_for_non_local_question() -> None:
    llm = FakeLLM("Python é uma linguagem de programação, senhor.")
    tts = FakeTextToSpeech()
    service = _build_service(llm=llm, tts=tts)

    response = service.handle("Explique o que é Python")

    assert response == "Python é uma linguagem de programação, senhor."
    assert llm.calls == ["Explique o que é Python"]
    assert tts.messages == ["Python é uma linguagem de programação, senhor."]


def test_assistant_service_speaks_command_ok_on_success() -> None:
    tts = FakeTextToSpeech()
    service = _build_service(
        command_interpreter=FakeCommandInterpreter(
            {"action": ActionType.OPEN_APP.value, "target": "discord"}
        ),
        action_executor=FakeActionExecutor(
            ActionResult(True, "Opened discord.", ActionType.OPEN_APP, "discord")
        ),
        tts=tts,
    )

    result = service.process("Jarvis, abra o Discord")

    assert result.action_result is not None
    assert result.action_result.success is True
    assert tts.messages == [STRINGS_PT.get("command_ok")]


def test_assistant_service_speaks_command_not_found_on_failure() -> None:
    tts = FakeTextToSpeech()
    service = _build_service(
        command_interpreter=FakeCommandInterpreter(
            {"action": ActionType.OPEN_APP.value, "target": "unknown"}
        ),
        action_executor=FakeActionExecutor(
            ActionResult(False, "Application 'unknown' was not found.", ActionType.OPEN_APP, "unknown")
        ),
        tts=tts,
    )

    result = service.process("Jarvis, abra o unknown")

    assert result.action_result is not None
    assert result.action_result.success is False
    assert tts.messages == [STRINGS_PT.get("command_not_found")]
