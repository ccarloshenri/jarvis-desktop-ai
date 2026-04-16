"""Low-level keyboard/window automation for Discord Desktop on Windows.

Discord is an Electron (Chromium) app, so its internals don't expose an
accessibility tree — but its global keyboard shortcuts work reliably:

  Ctrl+K   -> Quick Switcher (jump to any DM/server/channel by name)
  Ctrl+Alt+Up/Down -> previous/next unread (we use it as "back")
  Ctrl+Shift+M -> toggle microphone mute
  Ctrl+Shift+D -> toggle deafen
  Enter    -> send message in the focused composer
  Esc      -> dismiss

We follow the same pattern as `SpotifyKeyboardController`: pywin32 for
focus + key injection, clipboard paste for unicode-safe text input.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

LOGGER = logging.getLogger(__name__)

_DISCORD_PROCESS_NAMES = {"discord.exe", "discordptb.exe", "discordcanary.exe"}
_WINDOW_WAIT_SECONDS = 6.0
_WINDOW_POLL_INTERVAL = 0.15
_FOCUS_SETTLE_S = 0.12
_KEY_GAP_S = 0.025
_QUICK_SWITCHER_SETTLE_S = 0.18
_AFTER_SWITCH_SETTLE_S = 0.35

# Virtual-Key codes
_VK_CONTROL = 0x11
_VK_SHIFT = 0x10
_VK_MENU = 0x12  # Alt
_VK_K = 0x4B
_VK_M = 0x4D
_VK_D = 0x44
_VK_V = 0x56
_VK_UP = 0x26
_VK_RETURN = 0x0D
_VK_ESCAPE = 0x1B
_KEYEVENTF_KEYUP = 0x0002


class DiscordKeyboardController:
    """Concrete `IDiscordKeyboardController` for Windows Discord Desktop."""

    def __init__(self) -> None:
        self._win32_available = self._try_import_win32()

    def is_running(self) -> bool:
        try:
            import psutil

            for proc in psutil.process_iter(["name"]):
                name = (proc.info.get("name") or "").lower()
                if name in _DISCORD_PROCESS_NAMES:
                    return True
        except Exception as exc:
            LOGGER.warning("discord_is_running_failed", extra={"event_data": {"error": str(exc)}})
        return False

    def launch(self) -> bool:
        if self.is_running():
            return self.focus_window()
        path = self._find_discord_executable()
        if path is None:
            LOGGER.warning("discord_executable_not_found")
            return False
        try:
            subprocess.Popen([str(path)], close_fds=True)
        except OSError as exc:
            LOGGER.warning("discord_launch_failed", extra={"event_data": {"error": str(exc)}})
            return False
        return self._wait_for_window()

    def close(self) -> bool:
        try:
            import psutil

            terminated = False
            for proc in psutil.process_iter(["name"]):
                name = (proc.info.get("name") or "").lower()
                if name in _DISCORD_PROCESS_NAMES:
                    proc.terminate()
                    terminated = True
            return terminated
        except Exception as exc:
            LOGGER.warning("discord_close_failed", extra={"event_data": {"error": str(exc)}})
            return False

    def focus_window(self) -> bool:
        if not self._win32_available:
            return False
        try:
            import win32gui

            hwnd = self._find_window()
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
            LOGGER.warning("discord_focus_failed", extra={"event_data": {"error": str(exc)}})
            return False

    def quick_switcher(self, query: str) -> bool:
        if not self.focus_window():
            return False
        self._press_combo([_VK_CONTROL], _VK_K)
        time.sleep(_QUICK_SWITCHER_SETTLE_S)
        self.type_text(query)
        time.sleep(_QUICK_SWITCHER_SETTLE_S)
        self._press_key(_VK_RETURN)
        time.sleep(_AFTER_SWITCH_SETTLE_S)
        return True

    def type_text(self, text: str) -> None:
        if not text:
            return
        if not self._copy_to_clipboard(text):
            return
        self._press_combo([_VK_CONTROL], _VK_V)
        time.sleep(_KEY_GAP_S)

    def press_enter(self) -> None:
        self._press_key(_VK_RETURN)

    def hotkey_toggle_mute(self) -> None:
        if not self.focus_window():
            return
        self._press_combo([_VK_CONTROL, _VK_SHIFT], _VK_M)

    def hotkey_toggle_deafen(self) -> None:
        if not self.focus_window():
            return
        self._press_combo([_VK_CONTROL, _VK_SHIFT], _VK_D)

    def hotkey_previous_channel(self) -> None:
        if not self.focus_window():
            return
        self._press_combo([_VK_CONTROL, _VK_MENU], _VK_UP)

    # ---- internals ----

    def _try_import_win32(self) -> bool:
        try:
            import win32api  # noqa: F401
            import win32gui  # noqa: F401

            return True
        except ImportError:
            LOGGER.warning("discord_win32_unavailable")
            return False

    def _find_window(self) -> int:
        import win32gui

        target = {"hwnd": 0}

        def _enum(hwnd: int, _: object) -> None:
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return
                title = win32gui.GetWindowText(hwnd) or ""
                if "discord" in title.lower():
                    target["hwnd"] = hwnd
            except Exception:
                pass

        win32gui.EnumWindows(_enum, None)
        return target["hwnd"]

    def _wait_for_window(self) -> bool:
        deadline = time.monotonic() + _WINDOW_WAIT_SECONDS
        while time.monotonic() < deadline:
            if self.focus_window():
                return True
            time.sleep(_WINDOW_POLL_INTERVAL)
        return False

    def _find_discord_executable(self) -> Path | None:
        local = os.environ.get("LOCALAPPDATA")
        if not local:
            return None
        root = Path(local) / "Discord"
        if not root.exists():
            return None
        candidates = sorted(root.glob("app-*/Discord.exe"), reverse=True)
        return candidates[0] if candidates else None

    def _copy_to_clipboard(self, text: str) -> bool:
        try:
            import win32clipboard
            import win32con

            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
            finally:
                win32clipboard.CloseClipboard()
            return True
        except Exception as exc:
            LOGGER.warning("discord_clipboard_failed", extra={"event_data": {"error": str(exc)}})
            return False

    def _press_key(self, vk: int) -> None:
        if not self._win32_available:
            return
        import win32api

        win32api.keybd_event(vk, 0, 0, 0)
        time.sleep(_KEY_GAP_S)
        win32api.keybd_event(vk, 0, _KEYEVENTF_KEYUP, 0)
        time.sleep(_KEY_GAP_S)

    def _press_combo(self, modifiers: list[int], vk: int) -> None:
        if not self._win32_available:
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
