from __future__ import annotations

import logging

from jarvis.apps.base_app import BaseApp
from jarvis.apps.browser.browser_context import BrowserContext
from jarvis.apps.browser.interfaces import IBrowserController
from jarvis.apps.browser.services.browser_navigation_service import BrowserNavigationService
from jarvis.apps.browser.services.email_service import EmailService
from jarvis.apps.browser.services.search_service import SearchService
from jarvis.apps.browser.site_registry import SiteRegistry
from jarvis.enums.action_type import ActionType
from jarvis.models.action_result import ActionResult
from jarvis.models.command import Command

LOGGER = logging.getLogger(__name__)

_BROWSER_ACTIONS = {
    ActionType.BROWSER_OPEN,
    ActionType.BROWSER_CLOSE,
    ActionType.BROWSER_FOCUS,
    ActionType.BROWSER_OPEN_SITE,
    ActionType.BROWSER_OPEN_URL,
    ActionType.BROWSER_SEARCH_GOOGLE,
    ActionType.BROWSER_SEARCH_YOUTUBE,
    ActionType.BROWSER_SEARCH_IMAGES,
    ActionType.BROWSER_SEARCH_NEWS,
    ActionType.BROWSER_NEW_TAB,
    ActionType.BROWSER_CLOSE_TAB,
    ActionType.BROWSER_NEXT_TAB,
    ActionType.BROWSER_PREV_TAB,
    ActionType.BROWSER_BACK,
    ActionType.BROWSER_FORWARD,
    ActionType.BROWSER_RELOAD,
    ActionType.BROWSER_OPEN_EMAIL,
    ActionType.BROWSER_CHECK_UNREAD,
    ActionType.BROWSER_SEARCH_EMAIL_FROM,
    ActionType.BROWSER_SEARCH_EMAIL_SUBJECT,
    # SEARCH_WEB (legacy) is also routed here so the old rule-based
    # "pesquisa X" phrase keeps working without any changes in its path.
    ActionType.SEARCH_WEB,
}


class BrowserApp(BaseApp):
    """Facade aggregating browser context + navigation/search/email services."""

    def __init__(
        self,
        controller: IBrowserController,
        context: BrowserContext | None = None,
        site_registry: SiteRegistry | None = None,
    ) -> None:
        self._controller = controller
        self._context = context or BrowserContext()
        self._sites = site_registry or SiteRegistry()
        self._navigation = BrowserNavigationService(controller, self._context, self._sites)
        self._search = SearchService(controller, self._context)
        self._email = EmailService(controller, self._context)

    @property
    def name(self) -> str:
        return "browser"

    @property
    def context(self) -> BrowserContext:
        return self._context

    def can_handle(self, command: Command) -> bool:
        return command.action in _BROWSER_ACTIONS

    def execute(self, command: Command) -> ActionResult:
        action = command.action
        params = command.parameters or {}
        try:
            if action == ActionType.BROWSER_OPEN:
                ok = self._navigation.open_browser()
                return self._result(ok, command, "Opened browser.")
            if action == ActionType.BROWSER_CLOSE:
                ok = self._navigation.close_browser()
                return self._result(ok, command, "Closed browser.")
            if action == ActionType.BROWSER_FOCUS:
                ok = self._navigation.focus()
                return self._result(ok, command, "Focused browser.")
            if action == ActionType.BROWSER_OPEN_SITE:
                alias = (params.get("site") or command.target or "").strip()
                if not alias:
                    return self._result(False, command, "Missing site alias.")
                ok, url = self._navigation.open_site_by_alias(alias)
                if not ok:
                    return self._result(False, command, f"Unknown site '{alias}'.")
                return self._result(True, command, f"Opened {alias} ({url}).")
            if action == ActionType.BROWSER_OPEN_URL:
                url = (params.get("url") or command.target or "").strip()
                ok = self._navigation.open_url(url)
                return self._result(ok, command, f"Opened {url}." if ok else "Missing URL.")
            if action in (ActionType.BROWSER_SEARCH_GOOGLE, ActionType.SEARCH_WEB):
                query = (params.get("query") or command.target or "").strip()
                ok = self._search.google(query)
                return self._result(ok, command, f"Searched Google for '{query}'." if ok else "Empty query.")
            if action == ActionType.BROWSER_SEARCH_YOUTUBE:
                query = (params.get("query") or command.target or "").strip()
                ok = self._search.youtube(query)
                return self._result(ok, command, f"Searched YouTube for '{query}'.")
            if action == ActionType.BROWSER_SEARCH_IMAGES:
                query = (params.get("query") or command.target or "").strip()
                ok = self._search.images(query)
                return self._result(ok, command, f"Searched images for '{query}'.")
            if action == ActionType.BROWSER_SEARCH_NEWS:
                query = (params.get("query") or command.target or "").strip()
                ok = self._search.news(query)
                return self._result(ok, command, f"Searched news for '{query}'.")
            if action == ActionType.BROWSER_NEW_TAB:
                return self._result(self._navigation.new_tab(), command, "New tab.")
            if action == ActionType.BROWSER_CLOSE_TAB:
                return self._result(self._navigation.close_tab(), command, "Closed tab.")
            if action == ActionType.BROWSER_NEXT_TAB:
                return self._result(self._navigation.next_tab(), command, "Next tab.")
            if action == ActionType.BROWSER_PREV_TAB:
                return self._result(self._navigation.prev_tab(), command, "Previous tab.")
            if action == ActionType.BROWSER_BACK:
                return self._result(self._navigation.back(), command, "Back.")
            if action == ActionType.BROWSER_FORWARD:
                return self._result(self._navigation.forward(), command, "Forward.")
            if action == ActionType.BROWSER_RELOAD:
                return self._result(self._navigation.reload(), command, "Reloaded.")
            if action == ActionType.BROWSER_OPEN_EMAIL:
                filter_ = (params.get("filter") or "").strip().lower()
                if filter_ == "unread":
                    ok = self._email.open_unread()
                elif filter_ == "important":
                    ok = self._email.open_important()
                else:
                    ok = self._email.open_inbox()
                return self._result(ok, command, "Opened email.")
            if action == ActionType.BROWSER_CHECK_UNREAD:
                # URL-only backend: open the unread filter, but can't
                # actually report counts without a real API integration.
                ok = self._email.open_unread()
                return self._result(
                    ok,
                    command,
                    "Opened unread email (count not available without Gmail API).",
                )
            if action == ActionType.BROWSER_SEARCH_EMAIL_FROM:
                sender = (params.get("sender") or command.target or "").strip()
                ok = self._email.search_from(sender)
                return self._result(ok, command, f"Searched emails from {sender}.")
            if action == ActionType.BROWSER_SEARCH_EMAIL_SUBJECT:
                subject = (params.get("subject") or command.target or "").strip()
                ok = self._email.search_subject(subject)
                return self._result(ok, command, f"Searched emails with subject {subject}.")
        except Exception as exc:  # last-resort guard
            LOGGER.warning(
                "browser_action_failed",
                extra={"event_data": {"action": action.value, "error": str(exc)}},
            )
            return self._result(False, command, f"Browser action failed: {exc}")

        return self._result(False, command, f"Unhandled browser action '{action.value}'.")

    def _result(self, success: bool, command: Command, message: str) -> ActionResult:
        return ActionResult(success=success, message=message, action=command.action, target=command.target)
