from __future__ import annotations

from typing import Iterator, Sequence

from jarvis.config.strings import Strings
from jarvis.enums.action_type import ActionType
from jarvis.interfaces.iaction_executor import IActionExecutor
from jarvis.interfaces.illm import ILLM
from jarvis.models.action_result import ActionResult
from jarvis.models.chat_turn import ChatTurn
from jarvis.models.command import Command
from jarvis.models.llm_decision import LLMDecision
from jarvis.services.assistant_service import AssistantService
from jarvis.services.conversation_memory import ConversationMemory
from jarvis.utils.command_mapper import CommandMapper
from jarvis.utils.llm_response_parser import (
    ActionReady,
    ParseComplete,
    SpokenChunk,
    StreamEvent,
)


class FakeLLM(ILLM):
    def __init__(self, decision: LLMDecision | None = None, response: str = "ok") -> None:
        self._decision = decision
        self._response = response
        self.calls: list[str] = []
        self.history_calls: list[list[ChatTurn]] = []

    def decide(self, text: str, history: Sequence[ChatTurn] | None = None) -> LLMDecision:
        self.calls.append(text)
        self.history_calls.append(list(history or ()))
        if self._decision is not None:
            return self._decision
        return LLMDecision(type="chat", spoken_response=self._response)


class FakeTextToSpeech:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.stream_chunks: list[str] = []
        self.stream_ended: int = 0

    def speak(self, text: str) -> None:
        self.messages.append(text)

    def speak_stream_chunk(self, text: str) -> None:
        self.stream_chunks.append(text)

    def speak_stream_end(self) -> None:
        self.stream_ended += 1


class StreamingFakeLLM(FakeLLM):
    """FakeLLM extension that exposes `decide_streaming` so AssistantService
    takes the streaming code path. Yields events verbatim from the list
    passed at construction time."""

    def __init__(
        self,
        events: list[StreamEvent],
        decision: LLMDecision | None = None,
    ) -> None:
        super().__init__(decision=decision)
        self._events = events

    def decide_streaming(
        self,
        text: str,
        history: Sequence[ChatTurn] | None = None,
    ) -> Iterator[StreamEvent]:
        self.calls.append(text)
        self.history_calls.append(list(history or ()))
        yield from self._events


class FakeActionExecutor(IActionExecutor):
    def __init__(self, result: ActionResult) -> None:
        self._result = result
        self.executed: list[Command] = []

    def execute(self, command: Command) -> ActionResult:
        self.executed.append(command)
        return self._result


STRINGS_PT = Strings("pt-BR")


def _build_service(
    *,
    action_executor: FakeActionExecutor | None = None,
    llm: FakeLLM | None = None,
    tts: FakeTextToSpeech | None = None,
    conversation_memory: ConversationMemory | None = None,
) -> AssistantService:
    return AssistantService(
        strings=STRINGS_PT,
        action_executor=action_executor
        or FakeActionExecutor(ActionResult(True, "Opened.", ActionType.OPEN_APP, "discord")),
        llm=llm or FakeLLM(),
        text_to_speech=tts or FakeTextToSpeech(),
        command_mapper=CommandMapper(),
        conversation_memory=conversation_memory,
    )


def test_ignores_utterance_without_wake_word() -> None:
    tts = FakeTextToSpeech()
    llm = FakeLLM(response="não deveria aparecer")
    service = _build_service(llm=llm, tts=tts)

    result = service.process("o que voce acha disso")

    assert result.spoken_response == ""
    assert tts.messages == []
    assert llm.calls == []


def test_responds_to_bare_wake_word_with_greeting() -> None:
    tts = FakeTextToSpeech()
    service = _build_service(tts=tts)

    result = service.process("Jarvis")

    assert result.spoken_response == STRINGS_PT.get("greeting")
    assert tts.messages == [STRINGS_PT.get("greeting")]


def test_strips_wake_word_before_sending_to_llm() -> None:
    llm = FakeLLM()
    service = _build_service(llm=llm)

    service.handle("Jarvis, me conta uma piada")

    assert llm.calls == ["me conta uma piada"]


def test_accepts_stt_mishear_charges_as_wake_word() -> None:
    llm = FakeLLM()
    service = _build_service(llm=llm)

    result = service.process("charges manda um oi para yasmin no discord")

    assert result.spoken_response != ""
    assert llm.calls == ["manda um oi para yasmin no discord"]


def test_routes_chat_decision_to_tts() -> None:
    tts = FakeTextToSpeech()
    llm = FakeLLM(response="Python é uma linguagem, senhor.")
    service = _build_service(llm=llm, tts=tts)

    response = service.handle("Jarvis, o que é Python?")

    assert response == "Python é uma linguagem, senhor."
    assert tts.messages == ["Python é uma linguagem, senhor."]


def test_executes_action_from_llm_decision() -> None:
    tts = FakeTextToSpeech()
    decision = LLMDecision(
        type="action",
        spoken_response="Abrindo o Discord.",
        app="discord",
        action=ActionType.OPEN_APP.value,
        parameters={"target": "discord"},
    )
    llm = FakeLLM(decision=decision)
    executor = FakeActionExecutor(
        ActionResult(True, "Opened discord.", ActionType.OPEN_APP, "discord")
    )
    service = _build_service(llm=llm, tts=tts, action_executor=executor)

    result = service.process("Jarvis, abre o discord")

    assert result.command is not None
    assert result.command.action == ActionType.OPEN_APP
    assert result.command.target == "discord"
    # Action ack is now always built from Strings (localised + target
    # interpolated), not the raw llm_spoken, so it survives a Groq/EN
    # TTS swap without leaking Portuguese phrases through an English voice.
    assert tts.messages == [STRINGS_PT.get("ack_open_app", target="discord", label="discord")]


def test_speaks_command_not_found_when_action_fails() -> None:
    tts = FakeTextToSpeech()
    decision = LLMDecision(
        type="action",
        spoken_response="Abrindo unknown.",
        app="unknown",
        action=ActionType.OPEN_APP.value,
        parameters={"target": "unknown"},
    )
    llm = FakeLLM(decision=decision)
    executor = FakeActionExecutor(
        ActionResult(False, "Not found.", ActionType.OPEN_APP, "unknown")
    )
    service = _build_service(llm=llm, tts=tts, action_executor=executor)

    result = service.process("Jarvis, abre o unknown")

    assert result.action_result is not None
    assert result.action_result.success is False
    assert tts.messages == [
        STRINGS_PT.get("ack_open_app", target="unknown", label="unknown"),
        STRINGS_PT.get("command_not_found"),
    ]


def test_falls_back_to_chat_when_action_decision_has_invalid_target() -> None:
    tts = FakeTextToSpeech()
    decision = LLMDecision(
        type="action",
        spoken_response="Claro, senhor.",
        app=None,
        action="open_app",
        parameters={},
    )
    llm = FakeLLM(decision=decision)
    service = _build_service(llm=llm, tts=tts)

    result = service.process("Jarvis, algo sem alvo")

    assert result.command is None
    assert tts.messages == ["Claro, senhor."]


def test_streaming_chat_pipes_chunks_to_tts_and_closes_stream() -> None:
    tts = FakeTextToSpeech()
    chat_decision = LLMDecision(
        type="chat",
        spoken_response="Python é uma linguagem. Muito usada em dados.",
    )
    events: list[StreamEvent] = [
        SpokenChunk("Python é uma linguagem."),
        SpokenChunk("Muito usada em dados."),
        ParseComplete(decision=chat_decision),
    ]
    llm = StreamingFakeLLM(events=events, decision=chat_decision)
    service = _build_service(llm=llm, tts=tts)

    result = service.handle("Jarvis, o que é Python?")

    assert tts.stream_chunks == ["Python é uma linguagem.", "Muito usada em dados."]
    assert tts.stream_ended == 1
    # speak() must NOT be called — streaming already delivered the audio.
    assert tts.messages == []
    assert result == "Python é uma linguagem. Muito usada em dados."


def test_streaming_action_buffers_spoken_and_uses_normal_ack_path() -> None:
    tts = FakeTextToSpeech()
    action_decision = LLMDecision(
        type="action",
        spoken_response="Abrindo o Discord.",
        app="discord",
        action=ActionType.OPEN_APP.value,
        parameters={"target": "discord"},
    )
    events: list[StreamEvent] = [
        ActionReady(
            decision_type="action",
            app="discord",
            action=ActionType.OPEN_APP.value,
            parameters={"target": "discord"},
        ),
        SpokenChunk("Abrindo o Discord."),
        ParseComplete(decision=action_decision),
    ]
    llm = StreamingFakeLLM(events=events, decision=action_decision)
    executor = FakeActionExecutor(
        ActionResult(True, "Opened discord.", ActionType.OPEN_APP, "discord")
    )
    service = _build_service(llm=llm, tts=tts, action_executor=executor)

    result = service.process("Jarvis, abre o discord")

    # Action path: nothing should stream — the ack waits for the
    # correction service and is played through speak(). The spoken text
    # comes from Strings (localised, per-target), not the LLM.
    assert tts.stream_chunks == []
    assert tts.stream_ended == 0
    assert tts.messages == [STRINGS_PT.get("ack_open_app", target="discord", label="discord")]
    assert result.command is not None
    assert result.command.action == ActionType.OPEN_APP


def test_streaming_falls_back_on_parse_failure() -> None:
    tts = FakeTextToSpeech()
    events: list[StreamEvent] = [ParseComplete(decision=None)]
    llm = StreamingFakeLLM(events=events)
    service = _build_service(llm=llm, tts=tts)

    result = service.handle("Jarvis, algo bem confuso")

    assert tts.messages == [STRINGS_PT.get("no_response")]
    assert tts.stream_chunks == []
    assert result == STRINGS_PT.get("no_response")


def test_streaming_disabled_uses_blocking_decide() -> None:
    tts = FakeTextToSpeech()
    decision = LLMDecision(type="chat", spoken_response="Resposta direta.")
    events: list[StreamEvent] = [
        SpokenChunk("Este chunk não deve ser usado."),
        ParseComplete(decision=decision),
    ]
    llm = StreamingFakeLLM(events=events, decision=decision)
    service = AssistantService(
        strings=STRINGS_PT,
        action_executor=FakeActionExecutor(
            ActionResult(True, "Opened.", ActionType.OPEN_APP, "discord")
        ),
        llm=llm,
        text_to_speech=tts,
        command_mapper=CommandMapper(),
        llm_streaming=False,
    )

    result = service.handle("Jarvis, fala algo")

    assert tts.messages == ["Resposta direta."]
    assert tts.stream_chunks == []
    assert result == "Resposta direta."


def test_passes_history_to_llm_across_turns() -> None:
    llm = FakeLLM(response="Resposta dois.")
    memory = ConversationMemory(max_turns=10)
    service = _build_service(llm=llm, conversation_memory=memory)

    service.handle("Jarvis, quem descobriu o Brasil?")
    service.handle("Jarvis, e quando isso aconteceu?")

    assert llm.history_calls[0] == []
    second = llm.history_calls[1]
    assert [t.role for t in second] == ["user", "assistant"]
    assert second[0].content == "quem descobriu o Brasil?"
    assert second[1].content == "Resposta dois."
