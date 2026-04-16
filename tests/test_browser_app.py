from __future__ import annotations

from dataclasses import dataclass, field

from jarvis.apps.browser.browser_app import BrowserApp
from jarvis.enums.action_type import ActionType
from jarvis.models.command import Command


@dataclass
class FakeBrowserController:
    urls: list[tuple[str, bool]] = field(default_factory=list)
    closed: bool = False
    focused: bool = False
    hotkeys: list[str] = field(default_factory=list)
    open_ok: bool = True

    def open_url(self, url: str, new_tab: bool = True) -> bool:
        self.urls.append((url, new_tab))
        return self.open_ok

    def close_browser(self) -> bool:
        self.closed = True
        return True

    def focus_window(self) -> bool:
        self.focused = True
        return True

    def hotkey_new_tab(self) -> None:
        self.hotkeys.append("new_tab")

    def hotkey_close_tab(self) -> None:
        self.hotkeys.append("close_tab")

    def hotkey_next_tab(self) -> None:
        self.hotkeys.append("next_tab")

    def hotkey_prev_tab(self) -> None:
        self.hotkeys.append("prev_tab")

    def hotkey_back(self) -> None:
        self.hotkeys.append("back")

    def hotkey_forward(self) -> None:
        self.hotkeys.append("forward")

    def hotkey_reload(self) -> None:
        self.hotkeys.append("reload")


def _make_app() -> tuple[BrowserApp, FakeBrowserController]:
    controller = FakeBrowserController()
    return BrowserApp(controller=controller), controller


def test_browser_app_opens_site_by_alias() -> None:
    app, controller = _make_app()
    result = app.execute(
        Command(action=ActionType.BROWSER_OPEN_SITE, target="", parameters={"site": "github"})
    )
    assert result.success is True
    assert controller.urls == [("https://github.com", True)]
    assert app.context.current_site == "github"


def test_browser_app_rejects_unknown_site() -> None:
    app, controller = _make_app()
    result = app.execute(
        Command(action=ActionType.BROWSER_OPEN_SITE, target="", parameters={"site": "qwertyz"})
    )
    assert result.success is False
    assert "Unknown site" in result.message
    assert controller.urls == []


def test_browser_app_google_search_builds_query_url() -> None:
    app, controller = _make_app()
    result = app.execute(
        Command(
            action=ActionType.BROWSER_SEARCH_GOOGLE, target="", parameters={"query": "o que e bpmn"}
        )
    )
    assert result.success is True
    assert controller.urls[0][0] == "https://www.google.com/search?q=o+que+e+bpmn"
    assert app.context.last_search_query == "o que e bpmn"
    assert app.context.last_search_engine == "google"


def test_browser_app_youtube_search() -> None:
    app, controller = _make_app()
    result = app.execute(
        Command(action=ActionType.BROWSER_SEARCH_YOUTUBE, target="", parameters={"query": "lofi"})
    )
    assert result.success is True
    assert controller.urls[0][0] == "https://www.youtube.com/results?search_query=lofi"


def test_browser_app_open_email_inbox() -> None:
    app, controller = _make_app()
    result = app.execute(Command(action=ActionType.BROWSER_OPEN_EMAIL, target=""))
    assert result.success is True
    assert controller.urls[0][0] == "https://mail.google.com/mail/u/0/#inbox"


def test_browser_app_open_email_unread_filter() -> None:
    app, controller = _make_app()
    result = app.execute(
        Command(action=ActionType.BROWSER_OPEN_EMAIL, target="", parameters={"filter": "unread"})
    )
    assert result.success is True
    assert "is%3Aunread" in controller.urls[0][0]


def test_browser_app_search_email_from() -> None:
    app, controller = _make_app()
    result = app.execute(
        Command(
            action=ActionType.BROWSER_SEARCH_EMAIL_FROM, target="", parameters={"sender": "joao"}
        )
    )
    assert result.success is True
    assert "from%3Ajoao" in controller.urls[0][0]
    assert app.context.last_email_query == "from:joao"


def test_browser_app_tab_hotkeys() -> None:
    app, controller = _make_app()
    for action, expected in [
        (ActionType.BROWSER_NEW_TAB, "new_tab"),
        (ActionType.BROWSER_CLOSE_TAB, "close_tab"),
        (ActionType.BROWSER_NEXT_TAB, "next_tab"),
        (ActionType.BROWSER_PREV_TAB, "prev_tab"),
        (ActionType.BROWSER_BACK, "back"),
        (ActionType.BROWSER_FORWARD, "forward"),
        (ActionType.BROWSER_RELOAD, "reload"),
    ]:
        result = app.execute(Command(action=action, target=""))
        assert result.success is True
    assert controller.hotkeys == [
        "new_tab",
        "close_tab",
        "next_tab",
        "prev_tab",
        "back",
        "forward",
        "reload",
    ]


def test_browser_app_open_url_prepends_https_when_missing() -> None:
    app, controller = _make_app()
    result = app.execute(
        Command(action=ActionType.BROWSER_OPEN_URL, target="", parameters={"url": "example.com"})
    )
    assert result.success is True
    assert controller.urls[0][0] == "https://example.com"
