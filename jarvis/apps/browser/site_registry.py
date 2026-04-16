from __future__ import annotations

import re
from typing import Iterable

# Default aliases. Extend via SiteRegistry.register() at runtime.
_DEFAULT_SITES: dict[str, str] = {
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "yt": "https://www.youtube.com",
    "gmail": "https://mail.google.com/mail/u/0/#inbox",
    "email": "https://mail.google.com/mail/u/0/#inbox",
    "mail": "https://mail.google.com/mail/u/0/#inbox",
    "outlook": "https://outlook.live.com/mail/0/",
    "calendar": "https://calendar.google.com",
    "agenda": "https://calendar.google.com",
    "drive": "https://drive.google.com",
    "github": "https://github.com",
    "gitlab": "https://gitlab.com",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
    "linkedin": "https://www.linkedin.com",
    "whatsapp": "https://web.whatsapp.com",
    "whatsapp web": "https://web.whatsapp.com",
    # Note: "discord" and "spotify" are intentionally excluded — Jarvis has
    # dedicated desktop controllers for those apps, and an alias here would
    # hijack "abre o spotify" away from the desktop integration.
    "twitter": "https://x.com",
    "x": "https://x.com",
    "instagram": "https://www.instagram.com",
    "netflix": "https://www.netflix.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "gemini": "https://gemini.google.com",
    "reddit": "https://www.reddit.com",
    "notion": "https://www.notion.so",
    "figma": "https://www.figma.com",
    "fastapi": "https://fastapi.tiangolo.com",
    "mdn": "https://developer.mozilla.org",
    "python docs": "https://docs.python.org/3/",
}

_STRIP = re.compile(r"[^\w\s]")


class SiteRegistry:
    """Resolves human site names ("meu github", "o gmail") to URLs.

    Matching is accent-insensitive, case-insensitive, and tolerates common
    possessive fillers ("meu", "o", "a"). Extendable via register().
    """

    def __init__(self, sites: dict[str, str] | None = None) -> None:
        self._sites: dict[str, str] = dict(sites if sites is not None else _DEFAULT_SITES)

    def register(self, alias: str, url: str) -> None:
        clean = self._normalize(alias)
        if clean:
            self._sites[clean] = url

    def resolve(self, query: str) -> str | None:
        if not query:
            return None
        clean = self._normalize(query)
        if not clean:
            return None
        if clean in self._sites:
            return self._sites[clean]
        # Substring match on either direction — "meu github" contains "github".
        for alias, url in self._sites.items():
            if alias in clean or clean in alias:
                return url
        return None

    def known_aliases(self) -> Iterable[str]:
        return self._sites.keys()

    def _normalize(self, text: str) -> str:
        lowered = text.lower().strip()
        lowered = lowered.translate(
            str.maketrans("áàâãäéèêëíìîïóòôõöúùûüç", "aaaaaeeeeiiiiooooouuuuc")
        )
        lowered = re.sub(r"^(o|a|os|as|meu|minha|meus|minhas|the|my)\s+", "", lowered)
        lowered = _STRIP.sub(" ", lowered)
        return re.sub(r"\s+", " ", lowered).strip()
