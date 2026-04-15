from __future__ import annotations

from jarvis.enums.action_type import ActionType
from jarvis.implementations.llm.rule_based_command_interpreter import RuleBasedCommandInterpreter


def test_rule_based_command_interpreter_parses_open_command() -> None:
    payload = RuleBasedCommandInterpreter().interpret("Jarvis, open Discord")
    assert payload == {"action": ActionType.OPEN_APP.value, "target": "discord"}


def test_rule_based_command_interpreter_parses_close_command() -> None:
    payload = RuleBasedCommandInterpreter().interpret("Close notepad")
    assert payload == {"action": ActionType.CLOSE_APP.value, "target": "notepad"}


def test_rule_based_command_interpreter_returns_none_for_non_command() -> None:
    assert RuleBasedCommandInterpreter().interpret("What time is it?") is None


def test_rule_based_opens_spotify_even_with_stt_noise() -> None:
    payload = RuleBasedCommandInterpreter().interpret("Jardins abra Spotify")
    assert payload == {"action": ActionType.OPEN_APP.value, "target": "spotify"}


def test_rule_based_plays_spotify_when_play_verb_present() -> None:
    payload = RuleBasedCommandInterpreter().interpret("toca coldplay no spotify")
    assert payload == {"action": ActionType.PLAY_SPOTIFY.value, "target": "coldplay"}


def test_rule_based_opens_spotify_literal() -> None:
    payload = RuleBasedCommandInterpreter().interpret("abra o spotify")
    assert payload == {"action": ActionType.OPEN_APP.value, "target": "spotify"}


def test_rule_based_strips_trailing_fillers_from_target() -> None:
    payload = RuleBasedCommandInterpreter().interpret("Abra o Spotify aí")
    assert payload == {"action": ActionType.OPEN_APP.value, "target": "spotify"}


def test_rule_based_strips_multiple_trailing_fillers() -> None:
    payload = RuleBasedCommandInterpreter().interpret("Abra o chrome ai agora")
    assert payload == {"action": ActionType.OPEN_APP.value, "target": "chrome"}
