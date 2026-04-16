from __future__ import annotations

import re

from jarvis.apps.discord.discord_context import DiscordContext

_PRONOUN_REFS = re.compile(
    r"\b(ele|ela|nele|nela|com\s+ele|com\s+ela|pra\s+ele|pra\s+ela|pro\s+(mesmo|cara))\b",
    re.IGNORECASE,
)
_THIS_CONVO = re.compile(
    r"\b(essa\s+conversa|nessa\s+conversa|aqui\s+mesmo|aqui|nesse\s+canal|esse\s+canal)\b",
    re.IGNORECASE,
)
_THIS_SERVER = re.compile(r"\b(esse\s+servidor|nesse\s+servidor)\b", re.IGNORECASE)


class ContextResolver:
    """Resolves implicit references in user utterances using DiscordContext.

    Stateless. Given the raw text and the current context, returns a
    best-effort target name for actions like 'manda mensagem pra ele'.
    """

    def resolve_target_user(self, text: str, context: DiscordContext) -> str | None:
        if _PRONOUN_REFS.search(text):
            return context.last_user_mentioned or context.current_dm
        return None

    def is_referring_to_current_conversation(self, text: str) -> bool:
        return bool(_THIS_CONVO.search(text))

    def is_referring_to_current_server(self, text: str) -> bool:
        return bool(_THIS_SERVER.search(text))
