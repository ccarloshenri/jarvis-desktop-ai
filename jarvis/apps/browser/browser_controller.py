"""Default-browser automation for Jarvis.

URL opening uses Python's standard ``webbrowser`` module — cross-platform,
no driver or Selenium required. Tab/navigation controls use Win32 global
hotkeys routed to whichever browser window is currently focused (same
pattern as DiscordKeyboardController / SpotifyKeyboardController).

Browsers covered by the "close" operation (case-insensitive match on the
process name): Chrome, Edge, Firefox, Brave, Opera, Vivaldi, Arc.
"""

from __future__ import annotations

import logging
import time
import webbrowser

LOGGER = logging.getLogger(__name__)

_BROWSER_PROCESS_NAMES = {
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "brave.exe",
    "opera.exe",
    "vivaldi.exe",
    "arc.exe",
}

_KEY_GAP_S = 0.025
_FOCUS_SETTLE_S = 0.12

# Virtual-Key codes (Windows)
_VK_CONTROL = 0x11
_VK_SHIFT = 0x10
_VK_MENU = 0x12  # Alt
_VK_T = 0x54
_VK_W = 0x57
_VK_TAB = 0x09
_VK_LEFT = 0x25
_VK_RIGHT = 0x27
_VK_F5 = 0x74
_KEYEVENTF_KEYUP = 0x0002


class BrowserController:
    """Concrete IBrowserController for Windows + the default desktop browser."""

    def __init__(self) -> None:
        self._win32_available = self._try_import_win32()

    def open_url(self, url: str, new_tab: bool = True) -> bool:
        if not url:
            return False
        try:
            if new_tab:
                webbrowser.open_new_tab(url)
            else:
                webbrowser.open(url)
            return True
        except Exception as exc:
            LOGGER.warning("browser_open_url_failed", extra={"event_data": {"url": url, "error": str(exc)}})
            return False

    def close_browser(self) -> bool:
        try:
            import psutil

            terminated = False
            for proc in psutil.process_iter(["name"]):
                name = (proc.info.get("name") or "").lower()
                if name in _BROWSER_PROCESS_NAMES:
                    try:
                        proc.terminate()
                        terminated = True
                    except Exception:
                        pass
            return terminated
        except Exception as exc:
            LOGGER.warning("browser_close_failed", extra={"event_data": {"error": str(exc)}})
            return False

    def focus_window(self) -> bool:
        if not self._win32_available:
            return False
        try:
            import win32gui

            hwnd = self._find_browser_window()
            if hwnd == 0:
                return False
            try:
                win32gui.ShowWindow(hwnd, 9)  # SW_RESTORE
            except Exception:
                pass
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(_FOCUS_SETTLE_S)
            return True
        except Exception as exc:
            LOGGER.warning("browser_focus_failed", extra={"event_data": {"error": str(exc)}})
            return False

    def hotkey_new_tab(self) -> None:
        self._press_combo([_VK_CONTROL], _VK_T)

    def hotkey_close_tab(self) -> None:
        self._press_combo([_VK_CONTROL], _VK_W)

    def hotkey_next_tab(self) -> None:
        self._press_combo([_VK_CONTROL], _VK_TAB)

    def hotkey_prev_tab(self) -> None:
        self._press_combo([_VK_CONTROL, _VK_SHIFT], _VK_TAB)

    def hotkey_back(self) -> None:
        self._press_combo([_VK_MENU], _VK_LEFT)

    def hotkey_forward(self) -> None:
        self._press_combo([_VK_MENU], _VK_RIGHT)

    def hotkey_reload(self) -> None:
        self._press_key(_VK_F5)

    # ---- internals ----

    def _try_import_win32(self) -> bool:
        try:
            import win32api  # noqa: F401
            import win32gui  # noqa: F401

            return True
        except ImportError:
            LOGGER.warning("browser_win32_unavailable")
            return False

    def _find_browser_window(self) -> int:
        import win32gui
        import win32process

        try:
            import psutil
        except ImportError:
            return 0

        target = {"hwnd": 0}

        def _enum(hwnd: int, _: object) -> None:
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                try:
                    name = psutil.Process(pid).name().lower()
                except Exception:
                    return
                if name in _BROWSER_PROCESS_NAMES:
                    target["hwnd"] = hwnd
            except Exception:
                pass

        win32gui.EnumWindows(_enum, None)
        return target["hwnd"]

    def _press_key(self, vk: int) -> None:
        if not self._win32_available or not self.focus_window():
            return
        import win32api

        win32api.keybd_event(vk, 0, 0, 0)
        time.sleep(_KEY_GAP_S)
        win32api.keybd_event(vk, 0, _KEYEVENTF_KEYUP, 0)
        time.sleep(_KEY_GAP_S)

    def _press_combo(self, modifiers: list[int], vk: int) -> None:
        if not self._win32_available or not self.focus_window():
            return
        import win32api

        for mod in modifiers:
            win32api.keybd_event(mod, 0, 0, 0)
        time.sleep(_KEY_GAP_S)
        win32api.keybd_event(vk, 0, 0, 0)
        time.sleep(_KEY_GAP_S)
        win32api.keybd_event(vk, 0, _KEYEVENTF_KEYUP, 0)
        for mod in reversed(modifiers):
            win32api.keybd_event(mod, 0, _KEYEVENTF_KEYUP, 0)
        time.sleep(_KEY_GAP_S)
