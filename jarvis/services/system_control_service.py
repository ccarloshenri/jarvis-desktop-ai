"""Thin wrappers around OS-level controls — volume, clipboard,
screenshot, lock screen, folder open.

Everything here is Windows-first and fails soft on other platforms:
methods return False when the underlying API isn't available so the
executor can speak a generic error instead of crashing a worker
thread. Keeping this module isolated means one day porting to
macOS / Linux is a file-level edit, not a codebase-wide dig.
"""

from __future__ import annotations

import datetime
import io
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

LOGGER = logging.getLogger(__name__)


# Windows virtual-key codes for the system media buttons. Sending
# these via keybd_event triggers the same routines as pressing the
# physical keys on a keyboard — the audio mixer handles everything
# downstream (per-app volume, focus, unmute, etc).
_VK_VOLUME_MUTE = 0xAD
_VK_VOLUME_DOWN = 0xAE
_VK_VOLUME_UP = 0xAF
_KEYEVENTF_KEYUP = 0x0002


class SystemControlService:
    def __init__(self, screenshots_dir: Path | None = None) -> None:
        # Screenshots land in the user's Pictures/Jarvis folder by
        # default — a location Windows Explorer surfaces without the
        # user hunting through AppData.
        if screenshots_dir is None:
            pictures = Path.home() / "Pictures" / "Jarvis"
        else:
            pictures = screenshots_dir
        self._screenshots_dir = pictures

    # ── volume ────────────────────────────────────────────────────────

    def volume_up(self, steps: int = 3) -> bool:
        """Nudges system volume up by `steps * 2%` — each VK_VOLUME_UP
        press moves the master mixer by ~2% on default Windows."""
        return self._tap_media_key(_VK_VOLUME_UP, steps)

    def volume_down(self, steps: int = 3) -> bool:
        return self._tap_media_key(_VK_VOLUME_DOWN, steps)

    def volume_mute(self) -> bool:
        """Toggles mute — same key Windows uses, so hit it twice to
        un-mute from a muted state."""
        return self._tap_media_key(_VK_VOLUME_MUTE, 1)

    def _tap_media_key(self, vk: int, count: int) -> bool:
        if sys.platform != "win32":
            return False
        try:
            import ctypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            for _ in range(max(1, count)):
                user32.keybd_event(vk, 0, 0, 0)
                user32.keybd_event(vk, 0, _KEYEVENTF_KEYUP, 0)
                # A tiny gap between presses so the OS registers each
                # one discretely — consecutive keybd_events without a
                # pause sometimes collapse into a single tick.
                time.sleep(0.02)
            return True
        except Exception:
            LOGGER.exception("media_key_failed")
            return False

    # ── screenshot ───────────────────────────────────────────────────

    def screenshot(self) -> Path | None:
        """Capture the full desktop, save as PNG, return the path.
        None means the capture failed (missing PIL, permission denied,
        no display)."""
        try:
            from PIL import ImageGrab
        except ImportError:
            LOGGER.warning("screenshot_pillow_missing")
            return None
        try:
            self._screenshots_dir.mkdir(parents=True, exist_ok=True)
            image = ImageGrab.grab(all_screens=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = self._screenshots_dir / f"jarvis_{ts}.png"
            image.save(path)
            LOGGER.info(
                "screenshot_saved",
                extra={"event_data": {"path": str(path), "size": image.size}},
            )
            return path
        except Exception:
            LOGGER.exception("screenshot_failed")
            return None

    # ── clipboard ────────────────────────────────────────────────────

    def clipboard_read(self) -> str | None:
        """Return whatever text is currently on the Windows clipboard.
        None when the clipboard has no text content (e.g. image only).
        Fails soft on other platforms."""
        if sys.platform != "win32":
            return None
        try:
            import win32clipboard  # type: ignore[import-not-found]

            win32clipboard.OpenClipboard()
            try:
                if not win32clipboard.IsClipboardFormatAvailable(
                    win32clipboard.CF_UNICODETEXT
                ):
                    return None
                data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()
            return str(data) if data else None
        except Exception:
            LOGGER.exception("clipboard_read_failed")
            return None

    def clipboard_write(self, text: str) -> bool:
        if sys.platform != "win32" or not text:
            return False
        try:
            import win32clipboard  # type: ignore[import-not-found]

            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()
            return True
        except Exception:
            LOGGER.exception("clipboard_write_failed")
            return False

    # ── lock screen ───────────────────────────────────────────────────

    def lock_screen(self) -> bool:
        """LockWorkStation doesn't log the user out, just locks the
        screen — same effect as Win+L."""
        if sys.platform != "win32":
            return False
        try:
            import ctypes

            return bool(ctypes.WinDLL("user32").LockWorkStation())
        except Exception:
            LOGGER.exception("lock_screen_failed")
            return False

    # ── open folder ───────────────────────────────────────────────────

    def open_folder(self, name: str) -> bool:
        """Open a named system folder in Explorer. Resolves a few
        well-known shortcut names (Downloads, Documents, Desktop,
        Pictures, Music, Videos); anything else is treated as a
        literal path and passed through os.startfile."""
        if not name:
            return False
        resolved = self._resolve_folder(name.strip().lower())
        try:
            if sys.platform == "win32":
                os.startfile(str(resolved))  # type: ignore[attr-defined]
                return True
            subprocess.Popen(["xdg-open", str(resolved)])
            return True
        except OSError:
            LOGGER.exception("open_folder_failed")
            return False

    def _resolve_folder(self, name: str) -> Path:
        home = Path.home()
        aliases = {
            "downloads": home / "Downloads",
            "download": home / "Downloads",
            "documents": home / "Documents",
            "desktop": home / "Desktop",
            "pictures": home / "Pictures",
            "music": home / "Music",
            "videos": home / "Videos",
            "home": home,
            "user": home,
        }
        if name in aliases:
            return aliases[name]
        # Otherwise treat as a literal (relative paths resolved
        # against home so "scripts" means ~/scripts, not CWD).
        candidate = Path(name).expanduser()
        if not candidate.is_absolute():
            candidate = home / candidate
        return candidate
