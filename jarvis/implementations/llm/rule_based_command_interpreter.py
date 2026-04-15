from __future__ import annotations

import re

from jarvis.enums.action_type import ActionType
from jarvis.interfaces.icommand_interpreter import ICommandInterpreter
from jarvis.utils.llm_response_parser import LLMResponseParser


_OPEN_VERBS = (
    r"open|start|launch|run|"
    r"abra|abre|abrir|inicie|inicia|iniciar|execute|executa|executar|"
    r"roda|rodar|liga|ligar|lancar|lança|lanca"
)
_CLOSE_VERBS = (
    r"close|quit|exit|kill|"
    r"feche|fecha|fechar|encerre|encerra|encerrar|"
    r"pare|parar|desligue|desliga|desligar|mate|mata|matar|finaliza|finalizar"
)
_PLAY_VERBS = (
    r"play|"
    r"toca|toque|tocar|"
    r"reproduz|reproduza|reproduzir|"
    r"coloca|coloque|colocar|"
    r"bota|bote|botar|"
    r"poe|poem|pon|pos|poes"
)
_SEARCH_VERBS = (
    r"search|google|"
    r"pesquisa|pesquise|pesquisar|"
    r"procura|procure|procurar|"
    r"busca|busque|buscar"
)
_ARTICLES = r"\b(o|a|os|as|um|uma|the|app|application|program|programa|aplicativo)\b"
_TRAILING_FILLERS = re.compile(r"(?:\s+(ai|ali|aqui|tambem|ja|agora|rapido|logo))+$")

_FOR_ME_ANYWHERE = re.compile(r"\s*\b(para|pra|pro)\s+(mim|nos|voce|a\s+gente)\b\s*")
_SPOTIFY_CONNECTOR = re.compile(r"\s*\b(no|na|pelo|pela|em|on)\s+spotify\b\s*")
_SPOTIFY_BARE = re.compile(r"\bspotify\b")
_BROWSER_CONNECTOR = re.compile(
    r"\s*\b(no|na|pelo|pela|em|on)\s+(navegador|browser|google|chrome|firefox|internet|web)\b\s*"
)
_MUSIC_INTRO = re.compile(
    r"^(uma|um|a|o|as|os)?\s*"
    r"(musica|musicas|cancao|cancoes|som|track|song|audio)\s*"
    r"(da|do|de|das|dos|by|from)?\s*"
)
_LEADING_JUNK = re.compile(r"^(para|pra|pro|p)\s+(mim|nos|voce|a\s+gente)\s+")
_SPOTIFY_APP_ONLY = re.compile(rf"^({_OPEN_VERBS}|{_CLOSE_VERBS})\s+(o\s+|a\s+)?spotify\s*$")


class RuleBasedCommandInterpreter(ICommandInterpreter):
    def __init__(self) -> None:
        self._parser = LLMResponseParser()

    def interpret(self, text: str) -> dict[str, str] | None:
        cleaned = text.strip().lower()
        cleaned = self._strip_accents(cleaned)
        cleaned = re.sub(r"^jarvis[,\s]+", "", cleaned)
        cleaned = re.sub(r"\b(please|por favor|pf)\b", "", cleaned).strip()

        spotify_payload = self._try_spotify(cleaned)
        if spotify_payload is not None:
            return spotify_payload

        play_match = re.search(rf"\b({_PLAY_VERBS})\s+(.+)$", cleaned)
        if play_match:
            query = self._clean_query(play_match.group(2))
            if query:
                return self._parser.normalize_payload(
                    {"action": ActionType.PLAY_SPOTIFY.value, "target": query}
                )

        search_match = re.search(rf"\b({_SEARCH_VERBS})\s+(.+)$", cleaned)
        if search_match:
            query = self._clean_query(search_match.group(2), browser=True)
            if query:
                return self._parser.normalize_payload(
                    {"action": ActionType.SEARCH_WEB.value, "target": query}
                )

        open_match = re.search(rf"\b({_OPEN_VERBS})\s+(.+)$", cleaned)
        if open_match:
            return self._parser.normalize_payload(
                {"action": ActionType.OPEN_APP.value, "target": self._clean_target(open_match.group(2))}
            )

        close_match = re.search(rf"\b({_CLOSE_VERBS})\s+(.+)$", cleaned)
        if close_match:
            return self._parser.normalize_payload(
                {"action": ActionType.CLOSE_APP.value, "target": self._clean_target(close_match.group(2))}
            )
        return None

    def _try_spotify(self, cleaned: str) -> dict[str, str] | None:
        if "spotify" not in cleaned:
            return None
        if _SPOTIFY_APP_ONLY.match(cleaned):
            return None
        has_play_verb = re.search(rf"\b({_PLAY_VERBS})\b", cleaned) is not None
        has_spotify_connector = bool(_SPOTIFY_CONNECTOR.search(cleaned))
        if not (has_play_verb or has_spotify_connector):
            return None
        body = re.sub(rf"^({_PLAY_VERBS}|{_OPEN_VERBS})\s+", "", cleaned).strip()
        query = self._clean_query(body)
        if not query:
            return None
        return self._parser.normalize_payload(
            {"action": ActionType.PLAY_SPOTIFY.value, "target": query}
        )

    def _clean_target(self, target: str) -> str:
        value = re.sub(_ARTICLES, "", target)
        value = re.sub(r"[^\w\s\-.]", "", value)
        value = re.sub(r"\s+", " ", value).strip().lower()
        value = _TRAILING_FILLERS.sub("", value).strip()
        return value

    def _clean_query(self, target: str, browser: bool = False) -> str:
        value = target.strip()
        value = _FOR_ME_ANYWHERE.sub(" ", value).strip()
        value = _SPOTIFY_CONNECTOR.sub(" ", value).strip()
        if browser:
            value = _BROWSER_CONNECTOR.sub(" ", value).strip()
        value = _SPOTIFY_BARE.sub(" ", value).strip()
        value = _LEADING_JUNK.sub("", value).strip()
        value = _MUSIC_INTRO.sub("", value).strip()
        value = re.sub(r"^(da|do|de|das|dos)\s+", "", value).strip()
        value = re.sub(r"[^\w\s\-.]", "", value)
        return re.sub(r"\s+", " ", value).strip().lower()

    def _strip_accents(self, text: str) -> str:
        return text.translate(
            str.maketrans("áàâãäéèêëíìîïóòôõöúùûüç", "aaaaaeeeeiiiiooooouuuuc")
        )
