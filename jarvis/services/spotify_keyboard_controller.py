"""Controls Spotify Desktop using its native keyboard shortcuts.

Pros over the UIA approach: Spotify is CEF, so its internal widgets are a
web page and don't expose an accessibility tree — but its keyboard shortcuts
(Ctrl+L for search, Space for play/pause, arrow keys for navigation) DO
work reliably because Chromium routes them through its own input layer.

Pros over the Web API approach: no OAuth, no client_id, no tokens. Uses
only the local Spotify Desktop app.

Cons: it briefly takes keyboard focus. Not suitable if the user is typing
at the exact moment. Mitigated by running only when explicitly asked.

Flow (search_and_play):
1. Launch Spotify Desktop (no-op if already running).
2. Find Spotify window via win32gui + psutil (match by process name).
3. SetForegroundWindow to focus it.
4. Ctrl+L  -> focus search box.
5. Ctrl+A + Delete -> clear any leftover text.
6. Paste query via clipboard + Ctrl+V (unicode-safe, faster than per-char).
7. Enter -> open search results page.
8. Wait for results to render.
9. Navigate to first track and play it using arrow keys + Enter. Spotify's
   search page default focus lets us press Down/Tab to reach the first
   "Top result" track card, then Enter to play.

pywin32 is the primary driver (win32api.keybd_event). pyautogui is used
only as a last-resort fallback if pywin32 import fails.
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
_WINDOW_POLL_INTERVAL = 0.12
_FOCUS_SETTLE_S = 0.12
_KEY_GAP_S = 0.025
_SEARCH_RESULTS_WAIT_S = 0.5
_TITLE_POLL_TIMEOUT_S = 2.0
_TITLE_POLL_INTERVAL_S = 0.08
_POST_CLICK_POLL_S = 1.5
_IDLE_WINDOW_TITLES = {"spotify", "spotify premium", "spotify free"}

_SPOTIFY_GREEN_RGB = (30, 215, 96)  # #1ED760 — Spotify's updated brand green
_GREEN_TOLERANCE = 45
_MIN_PLAY_BUTTON_PIXELS = 40  # sampled pixels (with step=2, that's ~160 real pixels)
_PIXEL_STEP = 2  # sample every N pixels for speed
_SCAN_HEIGHT_RATIO = 0.70  # top portion of the window to scan

# Virtual-Key codes
_VK_CONTROL = 0x11
_VK_A = 0x41
_VK_K = 0x4B
_VK_V = 0x56
_VK_DELETE = 0x2E
_VK_RETURN = 0x0D
_VK_SPACE = 0x20
_KEYEVENTF_KEYUP = 0x0002


@dataclass
class _SpotifyWindow:
    hwnd: int
    title: str


class SpotifyKeyboardController:
    def __init__(self) -> None:
        pass

    def search_and_play(self, query: str) -> bool:
        query = query.strip()
        if not query:
            return False
        if sys.platform != "win32":
            LOGGER.warning("spotify_kb_unsupported_platform")
            return False

        self._launch_if_needed()
        window = self._wait_for_window(_WINDOW_WAIT_SECONDS)
        if window is None:
            LOGGER.warning("spotify_kb_window_not_found")
            return False

        if not self._focus(window):
            LOGGER.warning("spotify_kb_focus_failed")
            return False
        time.sleep(_FOCUS_SETTLE_S)

        if not self._open_quick_search():
            return False
        if not self._paste_query(query):
            return False
        time.sleep(_SEARCH_RESULTS_WAIT_S)
        # Strategy: compare window title before and after the first Enter.
        # Spotify reflects the currently playing track in the window title,
        # so a title change means something NEW started playing.
        #   - Track result    -> title changes to the new song -> done.
        #   - Artist/playlist -> title stays the same (old song keeps
        #     playing, or stays at "Spotify" if idle) -> send a second
        #     Enter to trigger play on the artist/playlist page.
        title_before = self._read_title(window.hwnd)
        # Attempt 1: first Enter commits Quick Search.
        #   - Track result -> plays immediately; title becomes "Song - Artist".
        #   - Artist/playlist -> opens the page; title unchanged.
        self._send_key(_VK_RETURN)
        title_after = self._poll_for_track_change(window.hwnd, title_before, _TITLE_POLL_TIMEOUT_S)
        attempts = ["enter"]

        # Attempt 2: if nothing new is playing, we're on an artist/playlist
        # page. Spotify has no keyboard shortcut to "play current page",
        # and Space toggles the OLD paused context instead of starting
        # new content. Fall back to finding the hero play button
        # dynamically (biggest Spotify-green blob in the upper half of
        # the window) and clicking it with pyautogui.
        if not self._is_new_track_title(title_before, title_after):
            clicked_at = self._find_and_click_play_button(window.hwnd)
            if clicked_at is not None:
                attempts.append(f"click@{clicked_at[0]},{clicked_at[1]}")
                title_after = self._poll_for_track_change(
                    window.hwnd, title_before, _POST_CLICK_POLL_S
                )

        played = self._is_new_track_title(title_before, title_after)
        LOGGER.info(
            "spotify_kb_played" if played else "spotify_kb_play_uncertain",
            extra={
                "event_data": {
                    "query": query,
                    "title_before": title_before,
                    "title_after": title_after,
                    "attempts": attempts,
                    "played": played,
                }
            },
        )
        return True

    def _poll_for_track_change(self, hwnd: int, baseline: str, timeout_s: float) -> str:
        deadline = time.perf_counter() + timeout_s
        latest = self._read_title(hwnd)
        while time.perf_counter() < deadline:
            latest = self._read_title(hwnd)
            if self._is_new_track_title(baseline, latest):
                return latest
            time.sleep(_TITLE_POLL_INTERVAL_S)
        return latest

    def _is_new_track_title(self, baseline: str, current: str) -> bool:
        if not current or current == baseline:
            return False
        if current.strip().lower() in _IDLE_WINDOW_TITLES:
            return False
        return " - " in current

    def _find_and_click_play_button(self, hwnd: int) -> tuple[int, int] | None:
        """Locate the hero Play button on the current Spotify page by
        scanning the window for the brand green (#1DB954) and picking
        the biggest contiguous green blob in the upper half of the page
        (the header area on artist/playlist pages). Click its centroid
        with pyautogui, then restore the previous mouse position so the
        user barely notices the interaction."""
        try:
            import win32gui
            from PIL import ImageGrab
        except ImportError:
            LOGGER.warning("spotify_kb_click_deps_missing")
            return None

        try:
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        except Exception as exc:
            LOGGER.warning("spotify_kb_click_rect_failed", extra={"event_data": {"error": str(exc)}})
            return None

        width = right - left
        height = bottom - top
        if width <= 0 or height <= 0:
            return None

        scan_bottom = top + int(height * _SCAN_HEIGHT_RATIO)
        bbox = (left, top, right, scan_bottom)

        try:
            screenshot = ImageGrab.grab(bbox=bbox, all_screens=True)
        except Exception as exc:
            LOGGER.warning("spotify_kb_click_grab_failed", extra={"event_data": {"error": str(exc)}})
            return None

        pixels = screenshot.load()
        scan_w, scan_h = screenshot.size
        target_r, target_g, target_b = _SPOTIFY_GREEN_RGB

        green_points: set[tuple[int, int]] = set()
        for y in range(0, scan_h, _PIXEL_STEP):
            for x in range(0, scan_w, _PIXEL_STEP):
                pixel = pixels[x, y]
                if (
                    abs(pixel[0] - target_r) < _GREEN_TOLERANCE
                    and abs(pixel[1] - target_g) < _GREEN_TOLERANCE
                    and abs(pixel[2] - target_b) < _GREEN_TOLERANCE
                ):
                    green_points.add((x, y))

        LOGGER.info(
            "spotify_kb_scan",
            extra={
                "event_data": {
                    "window_rect": [left, top, right, bottom],
                    "scan_size": [scan_w, scan_h],
                    "green_pixels": len(green_points),
                }
            },
        )

        if not green_points:
            LOGGER.warning("spotify_kb_no_green_pixels")
            return None

        biggest_cluster = self._biggest_cluster(green_points)
        if len(biggest_cluster) < _MIN_PLAY_BUTTON_PIXELS:
            LOGGER.warning(
                "spotify_kb_green_cluster_too_small",
                extra={"event_data": {"cluster_size": len(biggest_cluster), "min": _MIN_PLAY_BUTTON_PIXELS}},
            )
            return None

        cx = sum(p[0] for p in biggest_cluster) // len(biggest_cluster)
        cy = sum(p[1] for p in biggest_cluster) // len(biggest_cluster)
        abs_x = left + cx
        abs_y = top + cy

        if not self._click_at(abs_x, abs_y):
            return None
        return (abs_x, abs_y)

    def _biggest_cluster(self, points: set[tuple[int, int]]) -> list[tuple[int, int]]:
        visited: set[tuple[int, int]] = set()
        biggest: list[tuple[int, int]] = []
        for start in points:
            if start in visited:
                continue
            stack = [start]
            cluster: list[tuple[int, int]] = []
            while stack:
                current = stack.pop()
                if current in visited:
                    continue
                visited.add(current)
                cluster.append(current)
                x, y = current
                for dx, dy in (
                    (-_PIXEL_STEP, 0),
                    (_PIXEL_STEP, 0),
                    (0, -_PIXEL_STEP),
                    (0, _PIXEL_STEP),
                ):
                    neighbor = (x + dx, y + dy)
                    if neighbor in points and neighbor not in visited:
                        stack.append(neighbor)
            if len(cluster) > len(biggest):
                biggest = cluster
        return biggest

    def _click_at(self, x: int, y: int) -> bool:
        try:
            import pyautogui
        except ImportError:
            return False
        try:
            pyautogui.FAILSAFE = False
            original = pyautogui.position()
            pyautogui.click(x, y)
            pyautogui.moveTo(original.x, original.y, duration=0)
            return True
        except Exception as exc:
            LOGGER.warning("spotify_kb_click_failed", extra={"event_data": {"error": str(exc)}})
            return False

    def open_search_fallback(self, query: str) -> bool:
        try:
            os.startfile(f"spotify:search:{query}")  # type: ignore[attr-defined]
            return True
        except OSError:
            return False

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
            LOGGER.warning("spotify_kb_launch_failed", extra={"event_data": {"error": str(exc)}})

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

    def _read_title(self, hwnd: int) -> str:
        try:
            import win32gui
        except ImportError:
            return ""
        try:
            return win32gui.GetWindowText(hwnd) or ""
        except Exception:
            return ""

    def _focus(self, window) -> bool:
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
        except Exception as exc:
            LOGGER.debug("spotify_kb_set_foreground_failed", extra={"event_data": {"error": str(exc)}})
            return False

    def _open_quick_search(self) -> bool:
        """Ctrl+K opens Spotify's Quick Search overlay, which auto-focuses
        its input and whose default action on Enter is 'play first result'
        — music plays directly, artists open and auto-play, playlists
        open and auto-play."""
        return self._send_chord([_VK_CONTROL, _VK_K])

    def _paste_query(self, query: str) -> bool:
        if not self._set_clipboard(query):
            return self._type_fallback(query)
        time.sleep(_KEY_GAP_S)
        return self._send_chord([_VK_CONTROL, _VK_V])

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
            return self._pyautogui_press(vk)
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

    def _pyautogui_press(self, vk: int) -> bool:
        try:
            import pyautogui
        except ImportError:
            return False
        mapping = {
            _VK_RETURN: "enter",
            _VK_DELETE: "delete",
        }
        key = mapping.get(vk)
        if key is None:
            return False
        try:
            pyautogui.press(key)
            return True
        except Exception:
            return False

    def _type_fallback(self, text: str) -> bool:
        try:
            import pyautogui
        except ImportError:
            return False
        try:
            pyautogui.typewrite(text, interval=0.01)
            return True
        except Exception:
            return False
