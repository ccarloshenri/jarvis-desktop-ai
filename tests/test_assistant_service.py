from __future__ import annotations

from datetime import datetime

from jarvis.config.strings import Strings
from jarvis.enums.action_type import ActionType
from typing import Sequence

from jarvis.interfaces.iaction_executor import IActionExecutor
from jarvis.interfaces.illm import ILLM
from jarvis.models.action_result import ActionResult
from jarvis.models.chat_turn import ChatTurn
from jarvis.models.command import Command
from jarvis.models.llm_decision import LLMDecision
from jarvis.services.assistant_service import AssistantService
from jarvis.services.conversation_memory import ConversationMemory
from jarvis.services.local_intent_handler import LocalIntentHandler
from jarvis.utils.command_mapper import CommandMapper


class FakeLLM(ILLM):
    def __init__(
        self,
        response: str,
        decision: LLMDecision | None = None,
        is_fallback: bool = False,
    ) -> None:
        self._response = response
        self._decision = decision
        self._is_fallback = is_fallback
        self.calls: list[str] = []
        self.history_calls: list[list[ChatTurn]] = []

    @property
    def is_fallback(self) -> bool:
        return self._is_fallback

    def interpret(self, text: str) -> str:
        self.calls.append(text)
        return self._response

    def decide(self, text: str, history: Sequence[ChatTurn] | None = None) -> LLMDecision:
        self.calls.append(text)
        self.history_calls.append(list(history or ()))
        if self._decision is not None:
            return self._decision
        return LLMDecision(type="chat", spoken_response=self._response)


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
    conversation_memory: ConversationMemory | None = None,
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
        conversation_memory=conversation_memory,
    )


def test_assistant_service_answers_local_date_query_in_fallback_mode() -> None:
    tts = FakeTextToSpeech()
    service = _build_service(
        local_intent_handler=LocalIntentHandler(
            strings=STRINGS_PT, now_provider=lambda: datetime(2026, 4, 14, 15, 45)
        ),
        llm=FakeLLM("ignored", is_fallback=True),
        tts=tts,
    )

    response = service.handle("Jarvis, que dia é hoje?")

    expected = "Hoje é 14 de abril de 2026, senhor."
    assert response == expected
    assert tts.messages == [expected]


def test_assistant_service_answers_local_weather_query_in_fallback_mode() -> None:
    tts = FakeTextToSpeech()
    service = _build_service(
        llm=FakeLLM("ignored", is_fallback=True),
        tts=tts,
    )

    response = service.handle("Jarvis, vai chover hoje?")

    expected = STRINGS_PT.get("weather_unavailable")
    assert response == expected
    assert tts.messages == [expected]


def test_assistant_service_sends_weather_to_llm_when_available() -> None:
    llm = FakeLLM("Não tenho acesso à previsão do tempo, senhor.")
    tts = FakeTextToSpeech()
    service = _build_service(llm=llm, tts=tts)

    response = service.handle("Jarvis, vai chover amanhã?")

    assert response == "Não tenho acesso à previsão do tempo, senhor."
    assert llm.calls == ["vai chover amanhã?"]
    assert tts.messages == ["Não tenho acesso à previsão do tempo, senhor."]


def test_assistant_service_uses_llm_for_non_local_question() -> None:
    llm = FakeLLM("Python é uma linguagem de programação, senhor.")
    tts = FakeTextToSpeech()
    service = _build_service(llm=llm, tts=tts)

    response = service.handle("Jarvis, explique o que é Python")

    assert response == "Python é uma linguagem de programação, senhor."
    assert llm.calls == ["explique o que é Python"]
    assert tts.messages == ["Python é uma linguagem de programação, senhor."]


def test_assistant_service_speaks_ack_before_action() -> None:
    tts = FakeTextToSpeech()
    executor_calls: list[Command] = []

    class RecordingExecutor(IActionExecutor):
        def execute(self, command: Command) -> ActionResult:
            executor_calls.append(command)
            return ActionResult(True, "Opened discord.", ActionType.OPEN_APP, "discord")

    service = _build_service(
        command_interpreter=FakeCommandInterpreter(
            {"action": ActionType.OPEN_APP.value, "target": "discord"}
        ),
        action_executor=RecordingExecutor(),
        tts=tts,
    )

    result = service.process("Jarvis, abra o Discord")

    expected_ack = STRINGS_PT.get("ack_open_app", target="discord")
    assert result.action_result is not None
    assert result.action_result.success is True
    assert tts.messages == [expected_ack]
    assert result.spoken_response == expected_ack
    assert len(executor_calls) == 1


def test_assistant_service_executes_action_from_llm_decision() -> None:
    tts = FakeTextToSpeech()
    decision = LLMDecision(
        type="action",
        spoken_response="Abrindo o Discord.",
        app="discord",
        action=ActionType.OPEN_APP.value,
        parameters={"target": "discord"},
    )
    llm = FakeLLM("unused", decision=decision)
    executor = FakeActionExecutor(
        ActionResult(True, "Opened discord.", ActionType.OPEN_APP, "discord")
    )
    service = _build_service(llm=llm, tts=tts, action_executor=executor)

    result = service.process("Jarvis, poderia abrir o discord para mim")

    assert result.command is not None
    assert result.command.action == ActionType.OPEN_APP
    assert result.command.target == "discord"
    assert result.action_result is not None
    assert result.action_result.success is True
    assert tts.messages == ["Abrindo o Discord."]


def test_assistant_service_speaks_chat_decision_when_action_invalid() -> None:
    tts = FakeTextToSpeech()
    decision = LLMDecision(
        type="action",
        spoken_response="Claro, senhor.",
        app=None,
        action="open_app",
        parameters={},
    )
    llm = FakeLLM("unused", decision=decision)
    service = _build_service(llm=llm, tts=tts)

    result = service.process("Jarvis, algo sem alvo")

    assert result.command is None
    assert result.action_result is None
    assert tts.messages == ["Claro, senhor."]


def test_assistant_service_ignores_utterance_without_wake_word() -> None:
    tts = FakeTextToSpeech()
    llm = FakeLLM("resposta que nao deveria aparecer")
    service = _build_service(llm=llm, tts=tts)

    result = service.process("o que voce acha disso")

    assert result.spoken_response == ""
    assert result.command is None
    assert tts.messages == []
    assert llm.calls == []


def test_assistant_service_responds_to_bare_wake_word_with_greeting() -> None:
    tts = FakeTextToSpeech()
    service = _build_service(tts=tts)

    result = service.process("Jarvis")

    assert result.spoken_response == STRINGS_PT.get("greeting")
    assert tts.messages == [STRINGS_PT.get("greeting")]


def test_assistant_service_strips_wake_word_before_sending_to_llm() -> None:
    llm = FakeLLM("ok")
    service = _build_service(llm=llm)

    service.handle("Jarvis, me conta uma piada")

    assert llm.calls == ["me conta uma piada"]


def test_assistant_service_preserves_embedded_wake_word() -> None:
    llm = FakeLLM("ok")
    service = _build_service(llm=llm)

    service.handle("Jarvis, fala que foi o Jarvis que mandou")

    # Only the leading wake word is stripped; the embedded one stays.
    assert llm.calls == ["fala que foi o Jarvis que mandou"]


def test_assistant_service_accepts_stt_mishear_charges_as_wake_word() -> None:
    llm = FakeLLM("ok")
    tts = FakeTextToSpeech()
    service = _build_service(llm=llm, tts=tts)

    result = service.process("charges manda um oi para yasmin no discord")

    # Wake-gate must NOT have silenced this utterance.
    assert result.spoken_response != ""


def test_assistant_service_passes_history_to_llm_across_turns() -> None:
    llm = FakeLLM("Resposta dois.")
    memory = ConversationMemory(max_turns=10)
    service = _build_service(llm=llm, conversation_memory=memory)

    service.handle("Jarvis, quem descobriu o Brasil?")
    service.handle("Jarvis, e quando isso aconteceu?")

    assert len(llm.history_calls) == 2
    assert llm.history_calls[0] == []
    second_history = llm.history_calls[1]
    assert [t.role for t in second_history] == ["user", "assistant"]
    assert second_history[0].content == "quem descobriu o Brasil?"
    assert second_history[1].content == "Resposta dois."


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
    expected_ack = STRINGS_PT.get("ack_open_app", target="unknown")
    assert tts.messages == [expected_ack, STRINGS_PT.get("command_not_found")]
