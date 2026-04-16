from __future__ import annotations

from jarvis.enums.action_type import ActionType
from jarvis.implementations.llm.rule_based_command_interpreter import RuleBasedCommandInterpreter


def _interpret(text: str) -> dict | None:
    return RuleBasedCommandInterpreter().interpret(text)


def test_rule_based_opens_browser() -> None:
    assert _interpret("abre o navegador") == {"action": ActionType.BROWSER_OPEN.value, "parameters": {}}


def test_rule_based_open_github_by_alias() -> None:
    payload = _interpret("abre o github")
    assert payload is not None
    assert payload["action"] == ActionType.BROWSER_OPEN_SITE.value
    assert payload["parameters"]["site"] == "github"


def test_rule_based_open_gmail_via_meu_email() -> None:
    payload = _interpret("abre meu email")
    assert payload is not None
    assert payload["action"] == ActionType.BROWSER_OPEN_EMAIL.value


def test_rule_based_unknown_site_does_not_match() -> None:
    # "notepad" is not in the registry — should NOT route to browser_open_site.
    payload = _interpret("abre o notepad")
    assert payload is not None
    assert payload["action"] == ActionType.OPEN_APP.value


def test_rule_based_youtube_search() -> None:
    payload = _interpret("pesquisa video de lofi no youtube")
    assert payload is not None
    assert payload["action"] == ActionType.BROWSER_SEARCH_YOUTUBE.value
    assert payload["parameters"]["query"] == "lofi"


def test_rule_based_images_search() -> None:
    payload = _interpret("pesquisa imagens de gato")
    assert payload is not None
    assert payload["action"] == ActionType.BROWSER_SEARCH_IMAGES.value
    assert payload["parameters"]["query"] == "gato"


def test_rule_based_news_search() -> None:
    payload = _interpret("pesquisa noticias sobre ia")
    assert payload is not None
    assert payload["action"] == ActionType.BROWSER_SEARCH_NEWS.value
    assert payload["parameters"]["query"] == "ia"


def test_rule_based_new_tab() -> None:
    assert _interpret("abre uma aba nova") == {"action": ActionType.BROWSER_NEW_TAB.value, "parameters": {}}


def test_rule_based_close_tab() -> None:
    assert _interpret("fecha essa aba") == {"action": ActionType.BROWSER_CLOSE_TAB.value, "parameters": {}}


def test_rule_based_reload_page() -> None:
    assert _interpret("recarrega a pagina") == {"action": ActionType.BROWSER_RELOAD.value, "parameters": {}}


def test_rule_based_back() -> None:
    assert _interpret("volta pagina") == {"action": ActionType.BROWSER_BACK.value, "parameters": {}}


def test_rule_based_check_unread_email() -> None:
    payload = _interpret("tem algum email nao lido")
    assert payload is not None
    assert payload["action"] == ActionType.BROWSER_CHECK_UNREAD.value


def test_rule_based_search_email_from_sender() -> None:
    payload = _interpret("procura email do joao")
    assert payload is not None
    assert payload["action"] == ActionType.BROWSER_SEARCH_EMAIL_FROM.value
    assert payload["parameters"]["sender"] == "joao"
