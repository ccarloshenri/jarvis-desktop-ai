"""Visual "show off" routine — spawns a swarm of CMD windows and flies
them around the screen in a sequence of choreographed patterns.

The show runs as a chain of ~3-5 second segments, each picking a random
choreography (orbit, figure-eight, lissajous, horizontal chase, spiral,
grid pulse). Transitions between segments are eased cubically so the
windows slide from one pattern into the next rather than teleporting.

Window movement uses `BeginDeferWindowPos` / `EndDeferWindowPos` to
batch all N window moves into one atomic update per frame. Calling
`SetWindowPos` sequentially on 8 windows at 30+ FPS produces visible
staircase artefacts on Windows; the deferred batch renders as a single
DWM composition update and looks silky smooth.

Runs in a background thread so the main Jarvis pipeline keeps working.
"""

from __future__ import annotations

import logging
import math
import random
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

LOGGER = logging.getLogger(__name__)


_WINDOW_COUNT = 10
_WINDOW_W = 380
_WINDOW_H = 240
_TOTAL_SECONDS = 55.0  # ~12 segments + finale — longer, more dramatic
_SEGMENT_MIN_S = 2.8
_SEGMENT_MAX_S = 4.5
_FPS = 60
_FRAME_INTERVAL = 1.0 / _FPS
_TITLE_PREFIX = "JARVIS-SHOW"
# Spotify search syntax with explicit track/artist operators — forces
# the API to return the AC/DC "Back in Black" studio version instead of
# a cover, remix, or live cut that sometimes shows up first on a plain
# keyword search.
_BACK_IN_BLACK_QUERY = 'track:"Back in Black" artist:"AC/DC"'
_SPOTIFY_BOOT_GRACE_S = 2.5
# Small pause after search_and_play returns True so Spotify's audio
# pipeline has a beat to start producing actual sound. The PUT /play
# call returns ~50ms before the speakers catch up; leaving 450ms on
# top avoids kicking off the visuals before the riff lands.
_AUDIO_START_GRACE_S = 0.45

# Visual profiles the spawned cmd windows cycle through. Each drives a
# different "hacker aesthetic" section of the batch script, so the swarm
# on screen reads as a coordinated attack chain instead of ten clones.
_PROFILES = (
    "matrix",
    "nmap",
    "hex",
    "decrypt",
    "exploit",
    "sysmon",
)


# Each spawned cmd reads profile from arg %2. setlocal+enabledelayedexpansion
# is mandatory for `!random!` to re-evaluate inside loops — without it every
# iteration would print the same number.
_BATCH_BODY = r"""@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title %~1
set profile=%~2
if "%profile%"=="matrix" goto matrix
if "%profile%"=="nmap" goto nmap
if "%profile%"=="hex" goto hex
if "%profile%"=="decrypt" goto decrypt
if "%profile%"=="exploit" goto exploit
if "%profile%"=="sysmon" goto sysmon
goto matrix

:matrix
color 0A
echo [JARVIS] MATRIX SURVEILLANCE INITIATED
echo [JARVIS] tracing packets across .gov endpoints...
:matrix_loop
<nul set /p=" "
for /l %%i in (1,1,48) do <nul set /p="!random:~-1!"
echo.
ping -n 1 -w 40 127.0.0.1 >nul
goto matrix_loop

:nmap
color 0B
echo [JARVIS] PORT SCANNER v2.1
echo [JARVIS] sweeping target subnet /16...
:nmap_loop
set /a "p1=!random! %% 255"
set /a "p2=!random! %% 255"
set /a "p3=!random! %% 255"
set /a "port=!random! %% 65535"
echo [+] 10.!p1!.!p2!.!p3!:!port!  OPEN   tcp   ssh-stealth
ping -n 1 -w 55 127.0.0.1 >nul
set /a "port2=!random! %% 65535"
echo [+] 10.!p1!.!p2!.!p3!:!port2! FILTERED  rpc-beacon
ping -n 1 -w 40 127.0.0.1 >nul
goto nmap_loop

:hex
color 0E
echo [JARVIS] MEMORY DUMP 0x7FFE0000
echo [JARVIS] reading .text segment...
:hex_loop
set /a "addr=!random!"
<nul set /p="0x7FFE!random:~-4!  "
for /l %%i in (1,1,8) do <nul set /p="!random:~-2!!random:~-2! "
echo.
ping -n 1 -w 45 127.0.0.1 >nul
goto hex_loop

:decrypt
color 0D
echo [JARVIS] AES-256 KEY BRUTE-FORCE
echo [JARVIS] candidate keys/s: 1.8M
:decrypt_loop
<nul set /p="key: "
for /l %%i in (1,1,10) do <nul set /p="!random:~-1!!random:~-1!-"
echo.
set /a "match=!random! %% 100"
if !match! LSS 3 echo [!] partial match at offset !random! ^(skipping^)
ping -n 1 -w 50 127.0.0.1 >nul
goto decrypt_loop

:exploit
color 04
echo [JARVIS] CVE-2024-0815 exploit chain
echo [+] shellcode loaded into .text segment
echo [+] ROP gadgets located: 12
echo [+] overwriting return address...
:exploit_loop
set /a "offset=!random! %% 4096"
echo [+] 0x7FFF!random:~-4! -^> EIP  ^(offset !offset!^)
ping -n 1 -w 75 127.0.0.1 >nul
set /a "chance=!random! %% 100"
if !chance! LSS 12 echo [!] stack canary detected — rotating chain
ping -n 1 -w 60 127.0.0.1 >nul
goto exploit_loop

:sysmon
color 0F
echo [JARVIS] SYSTEM EVENT MONITOR
echo [JARVIS] pid,image,cpu,path
:sysmon_loop
set /a "pid=!random! %% 9999 + 1000"
set /a "cpu=!random! %% 100"
echo !pid!,svchost.exe,!cpu!%%,C:\Windows\System32
ping -n 1 -w 40 127.0.0.1 >nul
set /a "pid2=!random! %% 9999 + 1000"
echo !pid2!,jarvis.exe,!random:~-2!%%,C:\Stark\bin
ping -n 1 -w 45 127.0.0.1 >nul
goto sysmon_loop
"""


@dataclass(frozen=True, slots=True)
class _Pose:
    """Target position for one window at one frame. Kept as a plain
    dataclass (not a tuple) so choreographies can be read like keyframes
    without index-counting errors."""

    x: float
    y: float


@dataclass(frozen=True, slots=True)
class _Frame:
    """Full-layout snapshot at one moment — one Pose per window. The
    orchestrator computes the "target" layout from the current
    choreography and eases the visible layout toward it."""

    poses: tuple[_Pose, ...]


class ShowOffService:
    """One-shot `run()` kicks off the show in a background thread.
    Thread-safe to call again after completion — a guard prevents
    overlapping shows (so a double-trigger won't spawn 16 windows).

    Optional dependency: `spotify_controller` lets the show kick off a
    banger ("Back in Black" by default) as the soundtrack. If None, the
    show runs silent. Decoupled deliberately so the service stays
    usable without Spotify credentials configured."""

    def __init__(self, spotify_controller: object | None = None) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._spotify_controller = spotify_controller

    def set_spotify_controller(self, controller: object) -> None:
        """Late-bind the Spotify controller — the executor may hot-swap
        the controller mid-session (keyboard ↔ API) and we want the
        next show to pick up the latest instance."""
        self._spotify_controller = controller

    def is_running(self) -> bool:
        return self._running

    def run(self) -> bool:
        if sys.platform != "win32":
            LOGGER.info("show_off_skipped_non_windows")
            return False
        try:
            import win32gui  # noqa: F401
        except ImportError:
            LOGGER.warning("show_off_skipped_no_pywin32")
            return False
        with self._lock:
            if self._running:
                return False
            self._running = True
        thread = threading.Thread(target=self._run_show, name="jarvis-show-off", daemon=True)
        thread.start()
        return True

    def _run_show(self) -> None:
        try:
            self._run_show_impl()
        except Exception:
            LOGGER.exception("show_off_failed")
        finally:
            self._running = False

    def _run_show_impl(self) -> None:
        import win32con  # type: ignore[import-not-found]
        import win32gui  # type: ignore[import-not-found]

        # Soundtrack first, synchronously. The show is meant to *drop*
        # with the opening riff, not start in silence while Spotify
        # boots in the background. Order:
        #   1. Launch Spotify if it isn't running (2-3s boot).
        #   2. PUT /play Back in Black and block until the API returns
        #      success — search_and_play is synchronous.
        #   3. Brief grace (~450ms) so the audio actually starts.
        # Then we clear the stage and fire the visuals.
        self._start_soundtrack_blocking()

        # Clear the stage after the music is running: minimises every
        # top-level window (including Spotify — it keeps playing from
        # the tray just fine, and a visible Spotify window would ruin
        # the cmd-swarm aesthetic).
        self._minimise_other_windows(win32gui, win32con)

        batch_path = self._write_batch_script()
        processes: list[subprocess.Popen] = []
        try:
            titles: list[str] = []
            for i in range(_WINDOW_COUNT):
                title = f"{_TITLE_PREFIX}-{i:02d}-{random.randint(1000, 9999)}"
                titles.append(title)
                processes.append(self._spawn_cmd(batch_path, title))

            # Give cmd a beat to build its window + set the title before
            # we scan. EnumWindows is cheap so we poll up to 500ms.
            time.sleep(0.35)
            hwnds = self._resolve_hwnds(titles, win32gui)

            screen_w, screen_h = self._screen_size(win32gui)
            stage = _Stage(
                screen_w=screen_w,
                screen_h=screen_h,
                window_w=_WINDOW_W,
                window_h=_WINDOW_H,
                count=_WINDOW_COUNT,
            )

            # Opening pose: windows start off-screen (below) so the first
            # segment gets to slide them up dramatically. Initial visible
            # layout is also the starting point for easing.
            current = _offscreen_start(stage)
            self._apply_frame(hwnds, current, win32gui, win32con)

            segments = _plan_segments(_TOTAL_SECONDS)
            show_start = time.perf_counter()
            for segment in segments:
                if time.perf_counter() - show_start >= _TOTAL_SECONDS:
                    break
                current = self._run_segment(
                    segment,
                    starting=current,
                    stage=stage,
                    hwnds=hwnds,
                    win32gui=win32gui,
                    win32con=win32con,
                )

            # Finale: contract everything to the centre, then bail.
            self._run_segment(
                _Segment(name="contract", duration_s=0.8, choreography="contract"),
                starting=current,
                stage=stage,
                hwnds=hwnds,
                win32gui=win32gui,
                win32con=win32con,
            )
        finally:
            for proc in processes:
                try:
                    proc.terminate()
                except OSError:
                    pass
            try:
                batch_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _run_segment(
        self,
        segment: "_Segment",
        starting: _Frame,
        stage: "_Stage",
        hwnds: list[int],
        win32gui,
        win32con,
    ) -> _Frame:
        """Ease from `starting` to the per-frame target of the segment's
        choreography over `segment.duration_s`. Returns the last rendered
        frame so the next segment can start from it (no teleports)."""
        start_t = time.perf_counter()
        # Pull the easing direction fresh each iteration — target
        # positions themselves move within a segment (orbits rotate,
        # spirals spiral), and we want to chase the evolving target, not
        # a single keyframe snapshot.
        visible = starting
        deadline = start_t + segment.duration_s
        while True:
            now = time.perf_counter()
            if now >= deadline:
                break
            seg_t = (now - start_t) / segment.duration_s
            target = _choreography_frame(segment.choreography, seg_t, stage)
            # Cross-fade easing factor. Grows from 0 at segment start to
            # ~1 by segment end — higher fidelity tracking near the end
            # avoids the visible "still easing when the next segment
            # starts" artefact.
            blend = _ease_in_out_cubic(min(1.0, seg_t * 1.4))
            visible = _lerp_frame(visible, target, blend)
            self._apply_frame(hwnds, visible, win32gui, win32con)
            time.sleep(_FRAME_INTERVAL)
        return visible

    def _apply_frame(
        self,
        hwnds: list[int],
        frame: _Frame,
        win32gui,
        win32con,
    ) -> None:
        """Move every window in one deferred batch. BeginDeferWindowPos
        lets the DWM compositor apply all N moves in a single frame,
        which is what makes the motion look smooth instead of tearing
        across the desktop. HWND_TOPMOST each frame keeps the show on
        top even when Spotify launches mid-show and tries to steal
        focus — we DON'T want the music player stealing the stage."""
        active = [(h, p) for h, p in zip(hwnds, frame.poses) if h]
        if not active:
            return
        try:
            hdwp = win32gui.BeginDeferWindowPos(len(active))
        except Exception:
            for hwnd, pose in active:
                self._set_pos_safe(hwnd, pose, win32gui, win32con)
            return
        flags = win32con.SWP_NOACTIVATE
        for hwnd, pose in active:
            try:
                hdwp = win32gui.DeferWindowPos(
                    hdwp,
                    hwnd,
                    win32con.HWND_TOPMOST,
                    int(pose.x),
                    int(pose.y),
                    _WINDOW_W,
                    _WINDOW_H,
                    flags,
                )
            except Exception:
                # Skip one broken handle without aborting the whole
                # batch; user won't notice a single window stalling.
                continue
        try:
            win32gui.EndDeferWindowPos(hdwp)
        except Exception:
            LOGGER.debug("end_defer_window_pos_failed", exc_info=True)

    def _minimise_other_windows(self, win32gui, win32con) -> None:
        """Minimise every visible top-level window so the cmd swarm has
        a clean stage. We explicitly minimise Spotify and Jarvis too —
        Spotify keeps playing audio from the tray, and the user's
        command already landed so the HUD doesn't need to be visible
        during the show. Only the taskbar/desktop shell is skipped
        (hiding those would shove the cmd windows into weird positions
        against the bottom edge of the screen).

        Errors on individual windows are logged and skipped — one
        uncooperative app shouldn't abort the whole stage-clear.
        """
        skip_class_names = {
            "Shell_TrayWnd",  # Windows taskbar
            "Progman",  # Desktop shell
            "WorkerW",  # Secondary desktop window
            "Shell_SecondaryTrayWnd",  # Multi-monitor taskbar
        }
        # Only skip windows we're literally about to create as part of
        # the show (they won't exist yet at call time, but keep the
        # filter as a safety net if this gets called twice).
        skip_title_substrings = (_TITLE_PREFIX,)

        minimised = 0

        def _cb(hwnd, _):
            nonlocal minimised
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                class_name = win32gui.GetClassName(hwnd)
                if class_name in skip_class_names:
                    return True
                title = win32gui.GetWindowText(hwnd)
                if not title:
                    return True
                for skip in skip_title_substrings:
                    if skip.lower() in title.lower():
                        return True
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                minimised += 1
            except Exception:
                LOGGER.debug("minimise_window_failed", exc_info=True)
            return True

        try:
            win32gui.EnumWindows(_cb, None)
        except Exception:
            LOGGER.warning("enum_windows_failed_during_minimise", exc_info=True)
        LOGGER.info(
            "show_off_stage_cleared",
            extra={"event_data": {"minimised": minimised}},
        )

    def _start_soundtrack_blocking(self) -> None:
        """Synchronously kick off Back in Black and wait long enough for
        audio to actually begin. The caller is the show orchestrator,
        which uses this as a gate — no visuals until the music lands.

        If Spotify isn't available at all (no controller, no API key,
        network blocked), we log and return silently so the show still
        plays without a soundtrack rather than stalling forever.
        """
        controller = self._spotify_controller
        if controller is None:
            LOGGER.info("show_off_no_spotify")
            return
        if not hasattr(controller, "search_and_play"):
            LOGGER.info("show_off_spotify_no_search_and_play")
            return

        try:
            self._ensure_spotify_running()
        except Exception:
            LOGGER.exception("show_off_spotify_launch_failed")
            return

        try:
            started = bool(controller.search_and_play(_BACK_IN_BLACK_QUERY))
        except Exception:
            LOGGER.exception("show_off_soundtrack_failed")
            return

        if not started:
            LOGGER.warning(
                "show_off_soundtrack_start_declined",
                extra={"event_data": {"query": _BACK_IN_BLACK_QUERY}},
            )
            return

        # search_and_play returns as soon as the PUT /play request
        # succeeds, which is about half a second before audio actually
        # reaches the speakers. Short sleep here lines the riff up with
        # the cmd windows' entrance slide.
        time.sleep(_AUDIO_START_GRACE_S)
        LOGGER.info(
            "show_off_soundtrack_started",
            extra={"event_data": {"query": _BACK_IN_BLACK_QUERY}},
        )

    def _ensure_spotify_running(self) -> None:
        """Launch Spotify if no Spotify process is already running.

        Uses psutil to probe first (cheap) so we don't re-open Spotify
        and rip its focus every time the show is triggered. If it's
        absent, we open the `spotify:` URL handler and sleep a short
        grace period — the Web API call that follows needs a live
        device to dispatch playback to, which Spotify registers a
        second or two after launch.
        """
        try:
            import psutil

            for proc in psutil.process_iter(["name"]):
                name = (proc.info.get("name") or "").lower()
                if name.startswith("spotify"):
                    LOGGER.debug("spotify_already_running")
                    return
        except Exception:
            LOGGER.debug("psutil_probe_failed", exc_info=True)

        LOGGER.info("show_off_launching_spotify")
        try:
            import os

            # `spotify:` URI scheme — registered by the Spotify installer
            # on Windows. `os.startfile` hands it off to the shell so
            # Spotify launches the same way as double-clicking a
            # spotify:track:... link.
            os.startfile("spotify:")  # type: ignore[attr-defined]
        except OSError as exc:
            LOGGER.warning(
                "spotify_uri_launch_failed",
                extra={"event_data": {"error": str(exc)}},
            )
            return
        time.sleep(_SPOTIFY_BOOT_GRACE_S)

    def _set_pos_safe(self, hwnd, pose: _Pose, win32gui, win32con) -> None:
        try:
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOPMOST,
                int(pose.x),
                int(pose.y),
                _WINDOW_W,
                _WINDOW_H,
                win32con.SWP_NOACTIVATE,
            )
        except Exception:
            pass

    def _spawn_cmd(self, batch_path: Path, title: str) -> subprocess.Popen:
        # Randomised profile per window so the swarm reads as a
        # coordinated multi-stage operation (port scan + exploit +
        # memory dump + matrix rain, all at once) rather than ten
        # identical Matrix windows. Each profile has its own colour
        # palette and content rhythm.
        profile = random.choice(_PROFILES)
        return subprocess.Popen(
            ["cmd.exe", "/c", str(batch_path), title, profile],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            close_fds=True,
        )

    def _write_batch_script(self) -> Path:
        script = _BATCH_BODY.format(title="%~1")
        path = Path(tempfile.mkstemp(prefix="jarvis_show_", suffix=".bat")[1])
        path.write_text(script, encoding="utf-8")
        return path

    def _resolve_hwnds(self, titles: list[str], win32gui) -> list[int]:
        found: dict[str, int] = {}

        def _cb(hwnd, _):
            try:
                name = win32gui.GetWindowText(hwnd)
            except Exception:
                return True
            if name.startswith(_TITLE_PREFIX):
                found[name] = hwnd
            return True

        for _ in range(6):
            win32gui.EnumWindows(_cb, None)
            if len(found) >= len(titles):
                break
            time.sleep(0.1)
        return [found.get(t, 0) for t in titles]

    def _screen_size(self, win32gui) -> tuple[int, int]:
        hwnd = win32gui.GetDesktopWindow()
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        return right - left, bottom - top


# ---------- choreography primitives ----------


@dataclass(frozen=True, slots=True)
class _Stage:
    screen_w: int
    screen_h: int
    window_w: int
    window_h: int
    count: int

    @property
    def center_x(self) -> float:
        return self.screen_w / 2 - self.window_w / 2

    @property
    def center_y(self) -> float:
        return self.screen_h / 2 - self.window_h / 2

    @property
    def radius_x(self) -> float:
        return max(100, self.screen_w / 2 - self.window_w / 2 - 60)

    @property
    def radius_y(self) -> float:
        return max(80, self.screen_h / 2 - self.window_h / 2 - 60)


@dataclass(frozen=True, slots=True)
class _Segment:
    name: str
    duration_s: float
    choreography: str


_CHOREOGRAPHIES = (
    "orbit",
    "figure8",
    "lissajous",
    "horizontal_chase",
    "spiral_in",
    "grid_pulse",
    "wave",
)


def _plan_segments(total_seconds: float) -> list[_Segment]:
    """Build a randomised sequence of choreographies filling ~total
    seconds. Avoid repeating the same choreography back-to-back so the
    show feels like a progression rather than a loop."""
    segments: list[_Segment] = []
    remaining = total_seconds - 0.8  # reserve finale
    last: str | None = None
    while remaining > 0:
        duration = random.uniform(_SEGMENT_MIN_S, _SEGMENT_MAX_S)
        if duration > remaining:
            duration = max(1.2, remaining)
        choice = random.choice([c for c in _CHOREOGRAPHIES if c != last])
        segments.append(_Segment(name=choice, duration_s=duration, choreography=choice))
        last = choice
        remaining -= duration
    return segments


def _choreography_frame(name: str, t: float, stage: _Stage) -> _Frame:
    """Dispatch into the named choreography and return the target frame
    at parametric time `t` (0..1 within the segment)."""
    fn = _CHOREOGRAPHY_FNS[name]
    poses = tuple(fn(i, t, stage) for i in range(stage.count))
    return _Frame(poses=poses)


def _chor_orbit(i: int, t: float, stage: _Stage) -> _Pose:
    angle = (i / stage.count) * 2 * math.pi + t * math.pi * 1.5
    x = stage.center_x + stage.radius_x * math.cos(angle)
    y = stage.center_y + stage.radius_y * math.sin(angle)
    return _Pose(x, y)


def _chor_figure8(i: int, t: float, stage: _Stage) -> _Pose:
    # Lemniscate of Gerono: x = a sin(θ), y = a sin(θ)cos(θ). Offset
    # each window along the parametric path so they trail through the
    # figure rather than stack.
    theta = (i / stage.count) * 2 * math.pi + t * math.pi * 2
    x = stage.center_x + stage.radius_x * math.sin(theta)
    y = stage.center_y + stage.radius_y * math.sin(theta) * math.cos(theta)
    return _Pose(x, y)


def _chor_lissajous(i: int, t: float, stage: _Stage) -> _Pose:
    # 3:2 Lissajous — produces a satisfying braided path.
    phase = (i / stage.count) * 2 * math.pi
    x = stage.center_x + stage.radius_x * math.sin(3 * (t * math.pi * 2) + phase)
    y = stage.center_y + stage.radius_y * math.sin(2 * (t * math.pi * 2))
    return _Pose(x, y)


def _chor_horizontal_chase(i: int, t: float, stage: _Stage) -> _Pose:
    # Windows slide left-right at slightly different speeds so they
    # weave past each other. Y stays at evenly-spaced rows so it reads
    # as a band of traffic.
    lane = i % stage.count
    y = stage.center_y - stage.radius_y * 0.6 + lane * (stage.radius_y * 1.2 / stage.count)
    speed = 1.0 + (i % 3) * 0.35
    x = stage.center_x + stage.radius_x * math.sin(t * math.pi * 2 * speed + i * 0.7)
    return _Pose(x, y)


def _chor_spiral_in(i: int, t: float, stage: _Stage) -> _Pose:
    # Tightening spiral — radius shrinks with t.
    angle = (i / stage.count) * 2 * math.pi + t * math.pi * 4
    scale = 1.0 - t * 0.7
    x = stage.center_x + stage.radius_x * scale * math.cos(angle)
    y = stage.center_y + stage.radius_y * scale * math.sin(angle)
    return _Pose(x, y)


def _chor_grid_pulse(i: int, t: float, stage: _Stage) -> _Pose:
    # Arrange windows in a 4x2 grid centred on screen, with the whole
    # grid pulsing (scaling) in sync. Cheap but visually striking.
    cols = 4
    rows = 2
    col = i % cols
    row = i // cols
    cell_w = stage.radius_x * 2 / cols
    cell_h = stage.radius_y * 2 / rows
    gx = stage.center_x - stage.radius_x + col * cell_w + cell_w / 2 - stage.window_w / 2
    gy = stage.center_y - stage.radius_y + row * cell_h + cell_h / 2 - stage.window_h / 2
    pulse = 0.85 + 0.15 * math.sin(t * math.pi * 4)
    x = stage.center_x + (gx - stage.center_x) * pulse
    y = stage.center_y + (gy - stage.center_y) * pulse
    return _Pose(x, y)


def _chor_wave(i: int, t: float, stage: _Stage) -> _Pose:
    # Evenly-spaced horizontal line, each window oscillating vertically
    # with a phase shift — looks like a sine wave rippling across.
    spacing = (stage.radius_x * 1.8) / max(1, stage.count - 1)
    x = stage.center_x - stage.radius_x * 0.9 + i * spacing
    y = stage.center_y + stage.radius_y * 0.6 * math.sin(t * math.pi * 3 + i * 0.8)
    return _Pose(x, y)


def _chor_contract(i: int, t: float, stage: _Stage) -> _Pose:
    # Final flourish: windows converge to the centre. Used as the
    # closing segment before processes are terminated.
    start = _chor_orbit(i, 0.0, stage)
    ex = stage.center_x
    ey = stage.center_y
    t_eased = _ease_in_out_cubic(t)
    return _Pose(
        start.x + (ex - start.x) * t_eased,
        start.y + (ey - start.y) * t_eased,
    )


_CHOREOGRAPHY_FNS = {
    "orbit": _chor_orbit,
    "figure8": _chor_figure8,
    "lissajous": _chor_lissajous,
    "horizontal_chase": _chor_horizontal_chase,
    "spiral_in": _chor_spiral_in,
    "grid_pulse": _chor_grid_pulse,
    "wave": _chor_wave,
    "contract": _chor_contract,
}


# ---------- helpers ----------


def _offscreen_start(stage: _Stage) -> _Frame:
    """Initial layout: all windows sit just below the screen edge,
    evenly spread horizontally. First segment's ease will lift them
    into view and into whatever pattern it chose."""
    y = stage.screen_h + 40
    spacing = stage.screen_w / (stage.count + 1)
    poses = tuple(
        _Pose(spacing * (i + 1) - stage.window_w / 2, y) for i in range(stage.count)
    )
    return _Frame(poses=poses)


def _lerp_frame(a: _Frame, b: _Frame, alpha: float) -> _Frame:
    """Linear interpolation between two full-layout frames, pose by
    pose. Alpha is the easing weight (0 = fully at `a`, 1 = fully at
    `b`). Always yields `stage.count` poses."""
    poses = tuple(
        _Pose(
            a.poses[i].x + (b.poses[i].x - a.poses[i].x) * alpha,
            a.poses[i].y + (b.poses[i].y - a.poses[i].y) * alpha,
        )
        for i in range(min(len(a.poses), len(b.poses)))
    )
    return _Frame(poses=poses)


def _ease_in_out_cubic(t: float) -> float:
    """Smoothed cubic S-curve used for segment transitions. Keeps the
    start-of-segment slide and the end-of-segment settle feeling
    natural instead of linear."""
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return 4 * t * t * t
    p = 2 * t - 2
    return 0.5 * p * p * p + 1
