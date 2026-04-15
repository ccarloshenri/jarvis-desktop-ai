"""Opens a specific Spotify URI inside the local Spotify Desktop app by
driving Ctrl+K (Quick Search). Pasting a `spotify:track:ID`, `spotify:artist:ID`
or `spotify:playlist:ID` into Quick Search + Enter routes the app to that
exact item regardless of query matching, so once we have a resolved URI
(see `SpotifySearchProvider`) this is the most deterministic way to open it
without using the playback API.

Primary driver: pywin32. No pywinauto, no OCR, no UI tree walking.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

LOGGER = logging.getLogger(__name__)

_SPOTIFY_PROCESS_NAME = "spotify.exe"
_WINDOW_WAIT_SECONDS = 8.0
_WINDOW_POLL_INTERVAL = 0.2
_FOCUS_SETTLE_S = 0.25
_KEY_GAP_S = 0.04
_PASTE_SETTLE_S = 0.8

_VK_CONTROL = 0x11
_VK_K = 0x4B
_VK_V = 0x56
_VK_RETURN = 0x0D
_KEYEVENTF_KEYUP = 0x0002


@dataclass
class _SpotifyWindow:
    hwnd: int
    title: str


class SpotifyDesktopController:
    def open_uri(self, uri: str) -> bool:
        uri = uri.strip()
        if not uri:
            return False
        if sys.platform != "win32":
            LOGGER.warning("spotify_desktop_unsupported_platform")
            return False

        self._launch_if_needed()
        window = self._wait_for_window(_WINDOW_WAIT_SECONDS)
        if window is None:
            LOGGER.warning("spotify_desktop_window_not_found")
            return False

        if not self._focus(window):
            LOGGER.warning("spotify_desktop_focus_failed")
            return False
        time.sleep(_FOCUS_SETTLE_S)

        if not self._send_chord([_VK_CONTROL, _VK_K]):
            return False
        time.sleep(_KEY_GAP_S)
        if not self._set_clipboard(uri):
            return False
        if not self._send_chord([_VK_CONTROL, _VK_V]):
            return False
        time.sleep(_PASTE_SETTLE_S)
        return self._send_key(_VK_RETURN)

    def _launch_if_needed(self) -> None:
        try:
            import psutil
        except ImportError:
            psutil = None  # type: ignore[assignment]
        if psutil is not None:
            for proc in psutil.process_iter(["name"]):
                if (proc.info.get("name") or "").lower() == _SPOTIFY_PROCESS_NAME:
                    return
        exe = self._resolve_spotify_exe()
        try:
            if exe is not None:
                subprocess.Popen([str(exe)], close_fds=True)
            else:
                os.startfile("spotify:")  # type: ignore[attr-defined]
        except Exception as exc:
            LOGGER.warning("spotify_desktop_launch_failed", extra={"event_data": {"error": str(exc)}})

    def _resolve_spotify_exe(self) -> Path | None:
        candidates = [
            Path(os.environ.get("APPDATA", "")) / "Spotify" / "Spotify.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps" / "Spotify.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _wait_for_window(self, timeout: float) -> _SpotifyWindow | None:
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            window = self._find_window()
            if window is not None:
                return window
            time.sleep(_WINDOW_POLL_INTERVAL)
        return None

    def _find_window(self) -> _SpotifyWindow | None:
        try:
            import win32gui
            import win32process
        except ImportError:
            return None
        try:
            import psutil
        except ImportError:
            psutil = None  # type: ignore[assignment]

        spotify_pids: set[int] = set()
        if psutil is not None:
            for proc in psutil.process_iter(["pid", "name"]):
                if (proc.info.get("name") or "").lower() == _SPOTIFY_PROCESS_NAME:
                    spotify_pids.add(proc.info["pid"])

        matches: list[_SpotifyWindow] = []

        def _enum(hwnd: int, _param: object) -> bool:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
            except Exception:
                pid = 0
            title = win32gui.GetWindowText(hwnd) or ""
            if spotify_pids and pid in spotify_pids and title:
                matches.append(_SpotifyWindow(hwnd=hwnd, title=title))
            return True

        try:
            win32gui.EnumWindows(_enum, None)
        except Exception:
            return None
        if not matches:
            return None
        matches.sort(key=lambda w: len(w.title), reverse=True)
        return matches[0]

    def _focus(self, window: _SpotifyWindow) -> bool:
        try:
            import win32con
            import win32gui
        except ImportError:
            return False
        try:
            if win32gui.IsIconic(window.hwnd):
                win32gui.ShowWindow(window.hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(window.hwnd)
            return True
        except Exception:
            return False

    def _set_clipboard(self, text: str) -> bool:
        try:
            import win32clipboard
            import win32con
        except ImportError:
            return False
        for _ in range(3):
            try:
                win32clipboard.OpenClipboard()
                try:
                    win32clipboard.EmptyClipboard()
                    win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
                    return True
                finally:
                    win32clipboard.CloseClipboard()
            except Exception:
                time.sleep(0.05)
        return False

    def _send_key(self, vk: int) -> bool:
        try:
            import win32api
        except ImportError:
            return False
        try:
            win32api.keybd_event(vk, 0, 0, 0)
            time.sleep(_KEY_GAP_S)
            win32api.keybd_event(vk, 0, _KEYEVENTF_KEYUP, 0)
            return True
        except Exception:
            return False

    def _send_chord(self, vks: list[int]) -> bool:
        try:
            import win32api
        except ImportError:
            return False
        try:
            for vk in vks:
                win32api.keybd_event(vk, 0, 0, 0)
                time.sleep(0.01)
            time.sleep(_KEY_GAP_S)
            for vk in reversed(vks):
                win32api.keybd_event(vk, 0, _KEYEVENTF_KEYUP, 0)
                time.sleep(0.01)
            return True
        except Exception:
            return False
