from __future__ import annotations

from urllib.parse import quote_plus

from jarvis.apps.browser.browser_context import BrowserContext
from jarvis.apps.browser.interfaces import IBrowserController


class SearchService:
    """Google / YouTube / Images / News searches — URL based.

    All engines are reached by building a well-known query URL and
    delegating to the controller. Future: add a result-extraction
    backend (e.g. SerpAPI, Selenium) for "abre o primeiro resultado".
    """

    def __init__(self, controller: IBrowserController, context: BrowserContext) -> None:
        self._controller = controller
        self._context = context

    def google(self, query: str) -> bool:
        return self._open_query(f"https://www.google.com/search?q={quote_plus(query)}", query, "google")

    def youtube(self, query: str) -> bool:
        return self._open_query(
            f"https://www.youtube.com/results?search_query={quote_plus(query)}", query, "youtube"
        )

    def images(self, query: str) -> bool:
        return self._open_query(
            f"https://www.google.com/search?tbm=isch&q={quote_plus(query)}", query, "images"
        )

    def news(self, query: str) -> bool:
        return self._open_query(
            f"https://news.google.com/search?q={quote_plus(query)}", query, "news"
        )

    def _open_query(self, url: str, query: str, engine: str) -> bool:
        cleaned = query.strip()
        if not cleaned:
            return False
        if not self._controller.open_url(url, new_tab=True):
            return False
        self._context.remember_search(cleaned, engine)
        return True
