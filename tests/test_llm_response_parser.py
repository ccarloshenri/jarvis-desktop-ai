from __future__ import annotations

from jarvis.utils.llm_response_parser import parse_decision


def test_parses_clean_action_json() -> None:
    raw = '{"type":"action","app":"spotify","action":"open_app","parameters":{"target":"spotify"},"spoken_response":"Abrindo o Spotify."}'
    decision = parse_decision(raw)
    assert decision is not None
    assert decision.type == "action"
    assert decision.app == "spotify"
    assert decision.action == "open_app"
    assert decision.parameters == {"target": "spotify"}
    assert decision.spoken_response == "Abrindo o Spotify."


def test_parses_chat_with_nulls() -> None:
    raw = '{"type":"chat","app":null,"action":null,"parameters":{},"spoken_response":"Bom dia."}'
    decision = parse_decision(raw)
    assert decision is not None
    assert decision.type == "chat"
    assert decision.app is None
    assert decision.action is None


def test_strips_markdown_fences() -> None:
    raw = '```json\n{"type":"chat","spoken_response":"Oi."}\n```'
    decision = parse_decision(raw)
    assert decision is not None
    assert decision.spoken_response == "Oi."


def test_extracts_widest_json_block_when_prose_surrounds_it() -> None:
    raw = 'Claro senhor, aqui vai: {"type":"chat","spoken_response":"Oi."} Espero ter ajudado.'
    decision = parse_decision(raw)
    assert decision is not None
    assert decision.spoken_response == "Oi."


def test_returns_none_for_invalid_json() -> None:
    assert parse_decision("not json at all") is None


def test_returns_none_for_empty_spoken_response() -> None:
    raw = '{"type":"chat","spoken_response":""}'
    assert parse_decision(raw) is None


def test_returns_none_for_empty_input() -> None:
    assert parse_decision("") is None


def test_action_without_action_field_falls_back_to_chat() -> None:
    raw = '{"type":"action","spoken_response":"Hmm.","action":null}'
    decision = parse_decision(raw)
    assert decision is not None
    assert decision.type == "chat"


def test_invalid_type_defaults_to_chat() -> None:
    raw = '{"type":"sabotage","spoken_response":"Foo."}'
    decision = parse_decision(raw)
    assert decision is not None
    assert decision.type == "chat"
