from __future__ import annotations

import re
from typing import Any

from jarvis.apps.browser.site_registry import SiteRegistry
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

# ---- Discord rule patterns ----
_DISCORD_BARE = re.compile(r"\bdiscord\b")
# Accept trailing fillers like "para mim", "pra mim", "agora", "ai" so that
# "abre discord para mim" routes to DISCORD_OPEN rather than OPEN_APP with
# target="discord para mim".
_DISCORD_TRAILING_FILLER = r"(?:\s+(?:para|pra|pro)\s+(?:mim|nos|voce)|\s+(?:ai|agora|rapido|logo|aqui|tambem))*"
_DISCORD_OPEN_ONLY = re.compile(
    rf"^({_OPEN_VERBS})\s+(o\s+|a\s+)?discord{_DISCORD_TRAILING_FILLER}\s*$"
)
_DISCORD_CLOSE_ONLY = re.compile(
    rf"^({_CLOSE_VERBS})\s+(o\s+|a\s+)?discord{_DISCORD_TRAILING_FILLER}\s*$"
)
_DISCORD_SEND_DM = re.compile(
    r"^(?:manda|mande|mandar|envia|envie|enviar|escreve|escreva|escrever|diga|fala|falar)\s+"
    r"(?:um\s+|uma\s+)?"
    r"(?:"
        # "ai" covers the very common STT confusion of "oi" as "aí/ai".
        r"(?P<content>oi|ai|ei|ola|e\s+ai|bom\s+dia|boa\s+tarde|boa\s+noite|tchau|valeu|obrigado|obrigada)"
        r"|(?:mensagem|msg|recado|texto)"
    r")?\s*"
    r"(?:pro|pra|para)\s+(?:o\s+|a\s+)?(?P<who>[\w][\w\s\-.]*?)"
    r"(?:\s+no\s+discord)?"
    r"(?:\s*[:\-]\s*(?P<msg_colon>.+)"
    # Allow "dizendo que", "falando que", "fala que", "diz que", with optional
    # "e" connector: "... pro dudu e fala que ...".
    r"|(?:\s+e)?\s+(?:dizendo|falando|fala|diga|diz|dizer|falar)\s+(?:que\s+)?(?P<msg_saying>.+)"
    r"|\s*$)"
)
_DISCORD_SEND_DM_PRONOUN = re.compile(
    r"^(?:manda|mande|envia|envie|escreve|escreva|fala|falar|responde|responda)\s+"
    r"(?:pra|pro|para)?\s*(?P<who>ele|ela)\s*[:\-]\s*(?P<msg>.+)$"
)
_DISCORD_REPLY_CURRENT = re.compile(
    r"^(?:responde|responda|responder)\s+(?:essa\s+conversa|aqui|ai|nessa\s+conversa)\s*[:\-]\s*(?P<msg>.+)$"
)
_DISCORD_OPEN_DM = re.compile(
    r"^(?:abre|abra|abrir|chama|chamar)\s+(?:a\s+)?(?:conversa|dm|chat|privado)\s+"
    r"(?:com|do|da|de)\s+(?P<who>[\w][\w\s\-.]*?)(?:\s+no\s+discord)?\s*$"
)
_DISCORD_OPEN_CHANNEL = re.compile(
    r"^(?:abre|abra|abrir|entra|entrar|vai|va|joga|joga\s+pra)\s+"
    r"(?:no\s+|na\s+|o\s+|a\s+)?canal\s+(?P<channel>[\w][\w\s\-.]*?)"
    r"(?:\s+(?:do|da|no)\s+(?:servidor\s+)?(?P<server>[\w][\w\s\-.]*?))?"
    r"(?:\s+no\s+discord)?\s*$"
)
_DISCORD_OPEN_SERVER = re.compile(
    r"^(?:abre|abra|abrir|entra|entrar|vai|va)\s+(?:no\s+|na\s+|o\s+|a\s+)?servidor\s+"
    r"(?P<server>[\w][\w\s\-.]*?)(?:\s+no\s+discord)?\s*$"
)
_DISCORD_MUTE = re.compile(r"^(?:muta|mutar|me\s+muta|me\s+silencia|silencia|silenciar)\s*$")
_DISCORD_DEAFEN = re.compile(r"^(?:ensurdece|ensurdecer|me\s+ensurdece|deafen)\s*$")
_DISCORD_JOIN_VOICE = re.compile(
    r"^(?:entra|entrar|conecta|conectar)\s+(?:na\s+|no\s+|em\s+)?"
    r"(?:call|chamada|voz|canal\s+de\s+voz)\s+(?P<channel>[\w\s\-.]+?)\s*$"
)
_DISCORD_LEAVE_VOICE = re.compile(
    r"^(?:sai|sair|saia|desconecta|desconectar)\s+(?:da\s+|do\s+)?"
    r"(?:call|chamada|voz|canal\s+de\s+voz)\s*$"
)

# ---- Browser rule patterns ----
_BROWSER_OPEN_ONLY = re.compile(
    rf"^({_OPEN_VERBS})\s+(o\s+|a\s+)?(?:navegador|browser|chrome|edge|firefox|brave|opera)\s*$"
)
_BROWSER_CLOSE_ONLY = re.compile(
    rf"^({_CLOSE_VERBS})\s+(o\s+|a\s+)?(?:navegador|browser|chrome|edge|firefox|brave|opera)\s*$"
)
_BROWSER_NEW_TAB = re.compile(
    r"^(?:abre|abra|abrir|cria|criar|nova)\s+(?:uma\s+)?(?:nova\s+)?aba(?:\s+nova)?\s*$"
)
_BROWSER_CLOSE_TAB = re.compile(
    r"^(?:fecha|feche|fechar)\s+(?:essa\s+|esta\s+|a\s+)?aba(?:\s+atual)?\s*$"
)
_BROWSER_NEXT_TAB = re.compile(
    r"^(?:proxima|avanca|avanca\s+para\s+a\s+proxima|troca\s+de)\s+aba\s*$"
)
_BROWSER_PREV_TAB = re.compile(r"^(?:aba\s+anterior|volta\s+uma\s+aba)\s*$")
_BROWSER_BACK = re.compile(
    r"^(?:volta(?:r)?|volte)(?:\s+(?:pagina|uma\s+pagina|pra\s+pagina\s+anterior|a\s+pagina))?\s*$"
)
_BROWSER_FORWARD = re.compile(
    r"^(?:avanca(?:r)?|avance|proxima\s+pagina|vai\s+pra\s+proxima(?:\s+pagina)?)\s*$"
)
_BROWSER_RELOAD = re.compile(
    r"^(?:recarrega(?:r)?|recarregue|atualiza(?:r)?|atualize|f\s*5)(?:\s+(?:a\s+)?pagina)?\s*$"
)
_BROWSER_OPEN_SITE = re.compile(
    rf"^({_OPEN_VERBS})\s+(?:o\s+|a\s+|os\s+|as\s+|meu\s+|minha\s+|meus\s+|minhas\s+)?(?P<site>.+?)\s*$"
)
_BROWSER_GO_TO_SITE = re.compile(
    r"^(?:vai|va|ir|ir\s+pro|ir\s+para|ir\s+pra)\s+(?:o\s+|a\s+|os\s+|as\s+)?(?P<site>.+?)\s*$"
)
_BROWSER_SEARCH_YOUTUBE = re.compile(
    rf"^(?:{_SEARCH_VERBS})\s+(?:um\s+|uma\s+|o\s+|a\s+)?"
    r"(?:video|videos|musica|musicas)?\s*(?:de\s+)?"
    r"(?P<query>.+?)\s+(?:no|na|pelo|pela|em)\s+youtube\s*$"
)
_BROWSER_SEARCH_IMAGES = re.compile(
    rf"^(?:{_SEARCH_VERBS})\s+(?:umas\s+|uma\s+|imagens|fotos|uma\s+foto|uma\s+imagem)\s+"
    r"(?:de\s+|do\s+|da\s+|dos\s+|das\s+)?(?P<query>.+?)\s*$"
)
_BROWSER_SEARCH_NEWS = re.compile(
    rf"^(?:{_SEARCH_VERBS})\s+(?:uma\s+|umas\s+|as\s+|a\s+)?"
    r"(?:noticia|noticias)\s+(?:sobre|de|do|da|dos|das)\s+(?P<query>.+?)\s*$"
)
_BROWSER_OPEN_EMAIL = re.compile(
    r"^(?:abre|abra|abrir|checa|checar|ve|ver|vai\s+no)\s+"
    r"(?:meu\s+|o\s+meu\s+|o\s+|a\s+|minha\s+)?"
    r"(?:email|e-?mail|gmail|caixa\s+de\s+entrada|inbox)\s*$"
)
_BROWSER_UNREAD = re.compile(
    r"^(?:tem\s+algum|tem|ha|existe)\s+(?:email|e-?mail|mensagem)\s+"
    r"(?:nao\s+lido|novo|pendente)s?\s*\??$"
)
_BROWSER_EMAIL_FROM = re.compile(
    r"^(?:procura|procure|procurar|busca|busque|buscar|acha|achar)\s+"
    r"(?:email|e-?mail|mensagem)s?\s+(?:do|da|de|dos|das)\s+(?P<sender>.+?)\s*$"
)
_BROWSER_EMAIL_SUBJECT = re.compile(
    r"^(?:procura|procure|procurar|busca|busque|buscar)\s+"
    r"(?:email|e-?mail|mensagem)s?\s+(?:sobre|com\s+assunto)\s+(?P<subject>.+?)\s*$"
)


class RuleBasedCommandInterpreter(ICommandInterpreter):
    def __init__(self, site_registry: SiteRegistry | None = None) -> None:
        self._parser = LLMResponseParser()
        self._sites = site_registry or SiteRegistry()

    def interpret(self, text: str) -> dict[str, Any] | None:
        cleaned = text.strip().lower()
        cleaned = self._strip_accents(cleaned)
        cleaned = re.sub(r"^jarvis[,\s]+", "", cleaned)
        cleaned = re.sub(r"\b(please|por favor|pf)\b", "", cleaned).strip()

        discord_payload = self._try_discord(cleaned)
        if discord_payload is not None:
            return discord_payload

        browser_payload = self._try_browser(cleaned)
        if browser_payload is not None:
            return browser_payload

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

    def _try_discord(self, cleaned: str) -> dict | None:
        # Catch-all "abre/fecha o discord" first.
        if _DISCORD_OPEN_ONLY.match(cleaned):
            return {"action": ActionType.DISCORD_OPEN.value, "parameters": {}}
        if _DISCORD_CLOSE_ONLY.match(cleaned):
            return {"action": ActionType.DISCORD_CLOSE.value, "parameters": {}}

        # Voice toggles (must come before generic "muta X" being misread).
        if _DISCORD_MUTE.match(cleaned):
            return {"action": ActionType.DISCORD_TOGGLE_MUTE.value, "parameters": {}}
        if _DISCORD_DEAFEN.match(cleaned):
            return {"action": ActionType.DISCORD_TOGGLE_DEAFEN.value, "parameters": {}}
        if _DISCORD_LEAVE_VOICE.match(cleaned):
            return {"action": ActionType.DISCORD_LEAVE_VOICE.value, "parameters": {}}

        join = _DISCORD_JOIN_VOICE.match(cleaned)
        if join:
            return {
                "action": ActionType.DISCORD_JOIN_VOICE.value,
                "parameters": {"channel_name": join.group("channel").strip()},
            }

        # Pronoun-based send: "manda pra ele: oi" — must run before the named-user
        # rule, otherwise the broader regex captures "ele" as a literal user name.
        pronoun = _DISCORD_SEND_DM_PRONOUN.match(cleaned)
        if pronoun:
            return {
                "action": ActionType.DISCORD_SEND_MESSAGE.value,
                "parameters": {"target_type": "dm", "target_name": "", "message": pronoun.group("msg").strip()},
            }

        # Send to a named user (DM). Accepts three shapes:
        #   "manda mensagem pro renan: ja volto"     -> message via colon
        #   "manda mensagem pro renan dizendo ja vou"-> message via 'dizendo/falando'
        #   "manda um oi para yasmin"                -> message is the greeting itself
        send = _DISCORD_SEND_DM.match(cleaned)
        if send:
            who = send.group("who").strip()
            msg = (send.group("msg_colon") or send.group("msg_saying") or send.group("content") or "").strip()
            if who and msg:
                return {
                    "action": ActionType.DISCORD_SEND_MESSAGE.value,
                    "parameters": {"target_type": "dm", "target_name": who, "message": msg},
                }

        reply = _DISCORD_REPLY_CURRENT.match(cleaned)
        if reply:
            return {
                "action": ActionType.DISCORD_REPLY_CURRENT.value,
                "parameters": {"message": reply.group("msg").strip()},
            }

        dm = _DISCORD_OPEN_DM.match(cleaned)
        if dm:
            return {
                "action": ActionType.DISCORD_OPEN_DM.value,
                "parameters": {"target_name": dm.group("who").strip()},
            }

        channel = _DISCORD_OPEN_CHANNEL.match(cleaned)
        if channel:
            params = {"channel_name": channel.group("channel").strip()}
            server = channel.groupdict().get("server")
            if server:
                params["server_name"] = server.strip()
            return {"action": ActionType.DISCORD_OPEN_CHANNEL.value, "parameters": params}

        server_match = _DISCORD_OPEN_SERVER.match(cleaned)
        if server_match:
            return {
                "action": ActionType.DISCORD_OPEN_SERVER.value,
                "parameters": {"server_name": server_match.group("server").strip()},
            }

        return None

    def _try_browser(self, cleaned: str) -> dict | None:
        # Literal browser open/close first.
        if _BROWSER_OPEN_ONLY.match(cleaned):
            return {"action": ActionType.BROWSER_OPEN.value, "parameters": {}}
        if _BROWSER_CLOSE_ONLY.match(cleaned):
            return {"action": ActionType.BROWSER_CLOSE.value, "parameters": {}}

        # Tab / navigation hotkeys.
        if _BROWSER_NEW_TAB.match(cleaned):
            return {"action": ActionType.BROWSER_NEW_TAB.value, "parameters": {}}
        if _BROWSER_CLOSE_TAB.match(cleaned):
            return {"action": ActionType.BROWSER_CLOSE_TAB.value, "parameters": {}}
        if _BROWSER_NEXT_TAB.match(cleaned):
            return {"action": ActionType.BROWSER_NEXT_TAB.value, "parameters": {}}
        if _BROWSER_PREV_TAB.match(cleaned):
            return {"action": ActionType.BROWSER_PREV_TAB.value, "parameters": {}}
        if _BROWSER_BACK.match(cleaned):
            return {"action": ActionType.BROWSER_BACK.value, "parameters": {}}
        if _BROWSER_FORWARD.match(cleaned):
            return {"action": ActionType.BROWSER_FORWARD.value, "parameters": {}}
        if _BROWSER_RELOAD.match(cleaned):
            return {"action": ActionType.BROWSER_RELOAD.value, "parameters": {}}

        # Email intents (must run before generic "abre meu X" to catch "abre meu email").
        if _BROWSER_OPEN_EMAIL.match(cleaned):
            return {"action": ActionType.BROWSER_OPEN_EMAIL.value, "parameters": {}}
        if _BROWSER_UNREAD.match(cleaned):
            return {"action": ActionType.BROWSER_CHECK_UNREAD.value, "parameters": {}}
        email_from = _BROWSER_EMAIL_FROM.match(cleaned)
        if email_from:
            return {
                "action": ActionType.BROWSER_SEARCH_EMAIL_FROM.value,
                "parameters": {"sender": email_from.group("sender").strip()},
            }
        email_subj = _BROWSER_EMAIL_SUBJECT.match(cleaned)
        if email_subj:
            return {
                "action": ActionType.BROWSER_SEARCH_EMAIL_SUBJECT.value,
                "parameters": {"subject": email_subj.group("subject").strip()},
            }

        # Search intents (YouTube/images/news) — must run before the generic
        # SEARCH_WEB path so "pesquisa video de lofi no youtube" doesn't
        # leak into google search.
        yt = _BROWSER_SEARCH_YOUTUBE.match(cleaned)
        if yt:
            return {
                "action": ActionType.BROWSER_SEARCH_YOUTUBE.value,
                "parameters": {"query": yt.group("query").strip()},
            }
        img = _BROWSER_SEARCH_IMAGES.match(cleaned)
        if img:
            return {
                "action": ActionType.BROWSER_SEARCH_IMAGES.value,
                "parameters": {"query": img.group("query").strip()},
            }
        news = _BROWSER_SEARCH_NEWS.match(cleaned)
        if news:
            return {
                "action": ActionType.BROWSER_SEARCH_NEWS.value,
                "parameters": {"query": news.group("query").strip()},
            }

        # Open a known site by alias. Only match if the site registry
        # recognizes the target — otherwise fall through so "abre o
        # notepad" stays an OPEN_APP command.
        site_match = _BROWSER_OPEN_SITE.match(cleaned) or _BROWSER_GO_TO_SITE.match(cleaned)
        if site_match:
            candidate = site_match.group("site").strip()
            if self._sites.resolve(candidate) is not None:
                return {
                    "action": ActionType.BROWSER_OPEN_SITE.value,
                    "parameters": {"site": candidate},
                }

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
        value = _FOR_ME_ANYWHERE.sub(" ", target)
        value = re.sub(_ARTICLES, "", value)
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
