from __future__ import annotations

from jarvis.enums.action_type import ActionType
from jarvis.implementations.llm.rule_based_command_interpreter import RuleBasedCommandInterpreter


def _interpret(text: str) -> dict | None:
    return RuleBasedCommandInterpreter().interpret(text)


def test_rule_based_opens_discord() -> None:
    payload = _interpret("abre o discord")
    assert payload == {"action": ActionType.DISCORD_OPEN.value, "parameters": {}}


def test_rule_based_opens_discord_with_para_mim_filler() -> None:
    payload = _interpret("abre discord para mim")
    assert payload == {"action": ActionType.DISCORD_OPEN.value, "parameters": {}}


def test_rule_based_opens_discord_with_agora_filler() -> None:
    payload = _interpret("abre o discord agora")
    assert payload == {"action": ActionType.DISCORD_OPEN.value, "parameters": {}}


def test_rule_based_closes_discord() -> None:
    payload = _interpret("fecha o discord")
    assert payload == {"action": ActionType.DISCORD_CLOSE.value, "parameters": {}}


def test_rule_based_sends_message_to_named_user() -> None:
    payload = _interpret("manda mensagem pro renan: oi cara, ja volto")
    assert payload is not None
    assert payload["action"] == ActionType.DISCORD_SEND_MESSAGE.value
    assert payload["parameters"]["target_type"] == "dm"
    assert payload["parameters"]["target_name"] == "renan"
    assert payload["parameters"]["message"] == "oi cara, ja volto"


def test_rule_based_sends_message_with_pronoun() -> None:
    payload = _interpret("manda pra ele: ja vou")
    assert payload is not None
    assert payload["action"] == ActionType.DISCORD_SEND_MESSAGE.value
    assert payload["parameters"]["target_name"] == ""
    assert payload["parameters"]["message"] == "ja vou"


def test_rule_based_replies_current_conversation() -> None:
    payload = _interpret("responde aqui: entendido")
    assert payload is not None
    assert payload["action"] == ActionType.DISCORD_REPLY_CURRENT.value
    assert payload["parameters"]["message"] == "entendido"


def test_rule_based_opens_dm_with_user() -> None:
    payload = _interpret("abre a conversa com renan")
    assert payload is not None
    assert payload["action"] == ActionType.DISCORD_OPEN_DM.value
    assert payload["parameters"]["target_name"] == "renan"


def test_rule_based_opens_channel_in_server() -> None:
    payload = _interpret("abre o canal geral do servidor faculdade")
    assert payload is not None
    assert payload["action"] == ActionType.DISCORD_OPEN_CHANNEL.value
    assert payload["parameters"]["channel_name"].strip() == "geral"
    assert payload["parameters"]["server_name"].strip() == "faculdade"


def test_rule_based_mute() -> None:
    assert _interpret("muta") == {"action": ActionType.DISCORD_TOGGLE_MUTE.value, "parameters": {}}


def test_rule_based_join_voice_channel() -> None:
    payload = _interpret("entra na call amigos")
    assert payload is not None
    assert payload["action"] == ActionType.DISCORD_JOIN_VOICE.value
    assert payload["parameters"]["channel_name"] == "amigos"


def test_rule_based_leave_voice() -> None:
    assert _interpret("sai da call") == {"action": ActionType.DISCORD_LEAVE_VOICE.value, "parameters": {}}


def test_rule_based_send_dm_greeting_without_colon() -> None:
    payload = _interpret("manda um oi para yasmin")
    assert payload is not None
    assert payload["action"] == ActionType.DISCORD_SEND_MESSAGE.value
    assert payload["parameters"]["target_name"] == "yasmin"
    assert payload["parameters"]["message"] == "oi"


def test_rule_based_send_dm_greeting_with_article_and_discord_suffix() -> None:
    payload = _interpret("manda um oi para o dudu no discord")
    assert payload is not None
    assert payload["action"] == ActionType.DISCORD_SEND_MESSAGE.value
    assert payload["parameters"]["target_name"] == "dudu"
    assert payload["parameters"]["message"] == "oi"


def test_rule_based_send_dm_with_dizendo_clause() -> None:
    payload = _interpret("manda mensagem pro renan dizendo que ja volto")
    assert payload is not None
    assert payload["action"] == ActionType.DISCORD_SEND_MESSAGE.value
    assert payload["parameters"]["target_name"] == "renan"
    assert payload["parameters"]["message"] == "ja volto"


def test_rule_based_open_server_strips_trailing_discord() -> None:
    payload = _interpret("abre o servidor dos calabresas no discord")
    assert payload is not None
    assert payload["action"] == ActionType.DISCORD_OPEN_SERVER.value
    assert payload["parameters"]["server_name"] == "dos calabresas"


def test_rule_based_send_dm_tolerates_stt_ai_as_oi() -> None:
    payload = _interpret("manda um ai para o dudu no discord")
    assert payload is not None
    assert payload["action"] == ActionType.DISCORD_SEND_MESSAGE.value
    assert payload["parameters"]["target_name"] == "dudu"
    assert payload["parameters"]["message"] == "ai"


def test_rule_based_send_dm_accepts_fala_que_clause() -> None:
    payload = _interpret("manda mensagem para o dudu no discord e fala que eu ja volto")
    assert payload is not None
    assert payload["action"] == ActionType.DISCORD_SEND_MESSAGE.value
    assert payload["parameters"]["target_name"] == "dudu"
    assert payload["parameters"]["message"] == "eu ja volto"


def test_rule_based_open_channel_strips_trailing_discord() -> None:
    payload = _interpret("abre o canal geral no discord")
    assert payload is not None
    assert payload["action"] == ActionType.DISCORD_OPEN_CHANNEL.value
    assert payload["parameters"]["channel_name"] == "geral"
