from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BrowserContext:
    """Mutable web-activity context: what the user is looking at and what
    they most recently asked the browser to do.

    Used by the ContextResolver to turn phrases like "abre o primeiro
    resultado" or "volta pra página anterior" into concrete actions.
    """

    current_site: str | None = None  # alias, e.g. "gmail", "youtube"
    current_url: str | None = None
    last_search_query: str | None = None
    last_search_engine: str | None = None  # "google" | "youtube" | "images" | "news"
    last_email_query: str | None = None
    last_action: str | None = None
    history: list[str] = field(default_factory=list)

    def remember_site(self, alias: str, url: str | None = None) -> None:
        clean = alias.strip().lower()
        if not clean:
            return
        self.current_site = clean
        if url:
            self.current_url = url
        self._record(f"open_site:{clean}")

    def remember_url(self, url: str) -> None:
        clean = url.strip()
        if clean:
            self.current_url = clean
            self._record(f"open_url:{clean[:60]}")

    def remember_search(self, query: str, engine: str) -> None:
        q = query.strip()
        if q:
            self.last_search_query = q
            self.last_search_engine = engine
            self._record(f"search:{engine}:{q[:40]}")

    def remember_email_query(self, query: str) -> None:
        q = query.strip()
        if q:
            self.last_email_query = q
            self._record(f"email_search:{q[:40]}")

    def _record(self, action: str) -> None:
        self.last_action = action
        self.history.append(action)
        if len(self.history) > 20:
            self.history.pop(0)
