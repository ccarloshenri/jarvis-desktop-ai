from __future__ import annotations

from jarvis.utils.llm_response_parser import (
    ActionReady,
    ParseComplete,
    SpokenChunk,
    StreamingDecisionParser,
)


def _collect_events(parser: StreamingDecisionParser, chunks: list[str]) -> list:
    events: list = []
    for chunk in chunks:
        events.extend(parser.feed(chunk))
    events.extend(parser.finalize())
    return events


def test_action_then_spoken_single_delta() -> None:
    parser = StreamingDecisionParser()
    raw = (
        '{"type":"action","app":"spotify","action":"open_app",'
        '"parameters":{"target":"spotify"},"spoken_response":"Abrindo."}'
    )
    events = _collect_events(parser, [raw])
    kinds = [type(e) for e in events]
    assert ActionReady in kinds
    assert SpokenChunk in kinds
    assert kinds[-1] is ParseComplete
    action = next(e for e in events if isinstance(e, ActionReady))
    assert action.action == "open_app"
    assert action.parameters == {"target": "spotify"}
    complete = events[-1]
    assert isinstance(complete, ParseComplete)
    assert complete.decision is not None
    assert complete.decision.spoken_response == "Abrindo."


def test_chat_streams_spoken_chunks_across_deltas() -> None:
    parser = StreamingDecisionParser()
    deltas = [
        '{"type":"chat","app":null,"action":null,"parameters":{},',
        '"spoken_response":"Um buraco negro é uma região do espaço. ',
        "A gravidade nele é muito forte.",
        '"}',
    ]
    events = _collect_events(parser, deltas)
    chunks = [e for e in events if isinstance(e, SpokenChunk)]
    assert [c.text for c in chunks] == [
        "Um buraco negro é uma região do espaço.",
        "A gravidade nele é muito forte.",
    ]
    assert not any(isinstance(e, ActionReady) for e in events)


def test_action_ready_fires_before_spoken_chunks() -> None:
    parser = StreamingDecisionParser()
    deltas = [
        '{"type":"action","app":"spotify","action":"play_spotify",',
        '"parameters":{"target":"coldplay"},',
        '"spoken_response":"Tocando."}',
    ]
    events = _collect_events(parser, deltas)
    action_idx = next(i for i, e in enumerate(events) if isinstance(e, ActionReady))
    spoken_idx = next(i for i, e in enumerate(events) if isinstance(e, SpokenChunk))
    assert action_idx < spoken_idx


def test_json_escape_sequences_in_spoken_are_decoded() -> None:
    parser = StreamingDecisionParser()
    raw = (
        '{"type":"chat","action":null,"parameters":{},'
        '"spoken_response":"Ele disse \\"oi\\" para mim."}'
    )
    events = _collect_events(parser, [raw])
    complete = events[-1]
    assert isinstance(complete, ParseComplete)
    assert complete.decision is not None
    assert complete.decision.spoken_response == 'Ele disse "oi" para mim.'


def test_spoken_chunk_split_across_deltas_mid_escape() -> None:
    # The backslash arrives in one delta and the escaped character in the
    # next — the decoder must wait for the completion rather than emitting
    # a stray backslash.
    parser = StreamingDecisionParser()
    deltas = [
        '{"type":"chat","action":null,"parameters":{},"spoken_response":"a\\',
        'n b."}',
    ]
    events = _collect_events(parser, deltas)
    complete = events[-1]
    assert isinstance(complete, ParseComplete)
    assert complete.decision is not None
    assert complete.decision.spoken_response == "a\n b."


def test_invalid_json_yields_none_decision() -> None:
    parser = StreamingDecisionParser()
    events = _collect_events(parser, ["not json at all"])
    assert events[-1] == ParseComplete(decision=None)


def test_no_action_ready_when_action_field_is_null() -> None:
    parser = StreamingDecisionParser()
    raw = (
        '{"type":"chat","app":null,"action":null,"parameters":{},'
        '"spoken_response":"Bom dia."}'
    )
    events = _collect_events(parser, [raw])
    assert not any(isinstance(e, ActionReady) for e in events)


def test_short_single_sentence_emits_as_final_chunk() -> None:
    # Responses like "Abrindo." never hit a sentence boundary during feed
    # (no trailing whitespace) — they only get flushed by finalize().
    parser = StreamingDecisionParser()
    events = _collect_events(
        parser,
        ['{"type":"chat","action":null,"parameters":{},"spoken_response":"Abrindo."}'],
    )
    chunks = [e for e in events if isinstance(e, SpokenChunk)]
    assert [c.text for c in chunks] == ["Abrindo."]
