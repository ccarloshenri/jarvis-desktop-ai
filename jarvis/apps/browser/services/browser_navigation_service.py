from __future__ import annotations

from jarvis.apps.browser.browser_context import BrowserContext
from jarvis.apps.browser.interfaces import IBrowserController
from jarvis.apps.browser.site_registry import SiteRegistry


class BrowserNavigationService:
    """Opens URLs and dispatches tab/navigation hotkeys."""

    def __init__(
        self,
        controller: IBrowserController,
        context: BrowserContext,
        site_registry: SiteRegistry,
    ) -> None:
        self._controller = controller
        self._context = context
        self._sites = site_registry

    def open_browser(self) -> bool:
        # Opening a blank page is the closest webbrowser gives us to "just
        # launch the browser" without a target URL.
        return self._controller.open_url("about:blank", new_tab=False)

    def close_browser(self) -> bool:
        return self._controller.close_browser()

    def focus(self) -> bool:
        return self._controller.focus_window()

    def open_site_by_alias(self, alias: str) -> tuple[bool, str]:
        url = self._sites.resolve(alias)
        if url is None:
            return False, ""
        if not self._controller.open_url(url, new_tab=True):
            return False, url
        self._context.remember_site(alias=alias, url=url)
        return True, url

    def open_url(self, url: str) -> bool:
        if not url.strip():
            return False
        cleaned = url.strip()
        if not cleaned.startswith(("http://", "https://")):
            cleaned = f"https://{cleaned}"
        if not self._controller.open_url(cleaned, new_tab=True):
            return False
        self._context.remember_url(cleaned)
        return True

    def new_tab(self) -> bool:
        self._controller.hotkey_new_tab()
        return True

    def close_tab(self) -> bool:
        self._controller.hotkey_close_tab()
        return True

    def next_tab(self) -> bool:
        self._controller.hotkey_next_tab()
        return True

    def prev_tab(self) -> bool:
        self._controller.hotkey_prev_tab()
        return True

    def back(self) -> bool:
        self._controller.hotkey_back()
        return True

    def forward(self) -> bool:
        self._controller.hotkey_forward()
        return True

    def reload(self) -> bool:
        self._controller.hotkey_reload()
        return True
