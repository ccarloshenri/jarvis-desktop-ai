from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus

from jarvis.apps.base_app import BaseApp
from jarvis.enums.action_type import ActionType
from jarvis.interfaces.iaction_executor import IActionExecutor
from jarvis.interfaces.iapplication_finder import IApplicationFinder
from jarvis.interfaces.ispotify_controller import ISpotifyController
from jarvis.models.action_result import ActionResult
from jarvis.models.command import Command
from jarvis.services.show_off_service import ShowOffService
from jarvis.services.system_control_service import SystemControlService


class SystemActionExecutor(IActionExecutor):
    def __init__(
        self,
        application_finder: IApplicationFinder,
        spotify_controller: ISpotifyController | None = None,
        apps: list[BaseApp] | None = None,
        show_off_service: ShowOffService | None = None,
        system_control: SystemControlService | None = None,
    ) -> None:
        self._application_finder = application_finder
        self._spotify_controller = spotify_controller
        self._apps: list[BaseApp] = list(apps or [])
        self._show_off_service = show_off_service or ShowOffService(
            spotify_controller=spotify_controller
        )
        self._system_control = system_control or SystemControlService()
        # If the executor was handed both a show service and a spotify
        # controller, make sure the show can reach the controller —
        # covers the case where the caller wired them up independently.
        if spotify_controller is not None:
            self._show_off_service.set_spotify_controller(spotify_controller)

    def set_spotify_controller(self, controller: ISpotifyController) -> None:
        self._spotify_controller = controller
        # Propagate the new controller into the show service so the
        # next `jarvis, show off` uses it for the soundtrack.
        self._show_off_service.set_spotify_controller(controller)

    def execute(self, command: Command) -> ActionResult:
        for app in self._apps:
            if app.can_handle(command):
                return app.execute(command)
        if command.action == ActionType.OPEN_APP:
            return self._open_application(command)
        if command.action == ActionType.CLOSE_APP:
            return self._close_application(command)
        if command.action == ActionType.PLAY_SPOTIFY:
            return self._play_spotify(command)
        if command.action == ActionType.SEARCH_WEB:
            return self._search_web(command)
        if command.action == ActionType.SHOW_OFF:
            return self._show_off(command)
        if command.action == ActionType.VOLUME_UP:
            return self._volume_up(command)
        if command.action == ActionType.VOLUME_DOWN:
            return self._volume_down(command)
        if command.action == ActionType.VOLUME_MUTE:
            return self._volume_mute(command)
        if command.action == ActionType.SCREENSHOT:
            return self._screenshot(command)
        if command.action == ActionType.CLIPBOARD_READ:
            return self._clipboard_read(command)
        if command.action == ActionType.LOCK_SCREEN:
            return self._lock_screen(command)
        if command.action == ActionType.OPEN_FOLDER:
            return self._open_folder(command)
        raise ValueError(f"Unsupported action '{command.action.value}'.")

    def _volume_up(self, command: Command) -> ActionResult:
        ok = self._system_control.volume_up()
        return ActionResult(ok, "Volume up." if ok else "Volume control unavailable.", command.action, command.target)

    def _volume_down(self, command: Command) -> ActionResult:
        ok = self._system_control.volume_down()
        return ActionResult(ok, "Volume down." if ok else "Volume control unavailable.", command.action, command.target)

    def _volume_mute(self, command: Command) -> ActionResult:
        ok = self._system_control.volume_mute()
        return ActionResult(ok, "Toggled mute." if ok else "Volume control unavailable.", command.action, command.target)

    def _screenshot(self, command: Command) -> ActionResult:
        path = self._system_control.screenshot()
        if path is None:
            return ActionResult(False, "Could not capture screen.", command.action, command.target)
        return ActionResult(True, f"Screenshot saved to {path.name}.", command.action, command.target)

    def _clipboard_read(self, command: Command) -> ActionResult:
        text = self._system_control.clipboard_read()
        if not text:
            return ActionResult(False, "Clipboard empty.", command.action, command.target)
        # Stash the clipboard text in the result message so the TTS
        # layer can read it back to the user.
        preview = text if len(text) <= 180 else text[:177] + "…"
        return ActionResult(True, preview, command.action, command.target)

    def _lock_screen(self, command: Command) -> ActionResult:
        ok = self._system_control.lock_screen()
        return ActionResult(ok, "Locking." if ok else "Lock unavailable.", command.action, command.target)

    def _open_folder(self, command: Command) -> ActionResult:
        target = command.target or (command.parameters or {}).get("folder", "")
        ok = self._system_control.open_folder(target)
        if ok:
            return ActionResult(True, f"Opened {target}.", command.action, command.target)
        return ActionResult(False, f"Could not open folder '{target}'.", command.action, command.target)

    def _show_off(self, command: Command) -> ActionResult:
        started = self._show_off_service.run()
        if started:
            return ActionResult(True, "Show started.", command.action, command.target)
        return ActionResult(
            False, "Show already running or unsupported platform.", command.action, command.target
        )

    def _play_spotify(self, command: Command) -> ActionResult:
        query = command.target.strip()
        if not query:
            return ActionResult(False, "Empty Spotify query.", command.action, command.target)

        if self._spotify_controller is not None and self._spotify_controller.search_and_play(query):
            return ActionResult(
                True,
                f"Playing '{query}' on Spotify.",
                command.action,
                command.target,
            )

        if self._spotify_controller is not None:
            self._spotify_controller.open_search_fallback(query)
        return ActionResult(
            False,
            f"Could not play '{query}' on Spotify.",
            command.action,
            command.target,
        )

    def _search_web(self, command: Command) -> ActionResult:
        query = command.target.strip()
        if not query:
            return ActionResult(False, "Empty search query.", command.action, command.target)
        url = f"https://www.google.com/search?q={quote_plus(query)}"
        try:
            webbrowser.open(url)
            return ActionResult(True, f"Searched the web for '{query}'.", command.action, command.target)
        except Exception as exc:
            return ActionResult(False, str(exc), command.action, command.target)

    def _open_application(self, command: Command) -> ActionResult:
        application_path = self._application_finder.find(command.target)
        if application_path is None:
            return ActionResult(False, f"Application '{command.target}' was not found.", command.action, command.target)
        try:
            self._launch(application_path)
            return ActionResult(True, f"Opened {command.target}.", command.action, command.target)
        except OSError as exc:
            return ActionResult(False, str(exc), command.action, command.target)

    def _launch(self, application_path: str) -> None:
        suffix = Path(application_path).suffix.lower()
        if sys.platform == "win32" and suffix in {".lnk", ".url", ".appref-ms"}:
            os.startfile(application_path)  # type: ignore[attr-defined]
            return
        subprocess.Popen([application_path], close_fds=True)

    def _close_application(self, command: Command) -> ActionResult:
        application_path = self._application_finder.find(command.target)
        if application_path is None:
            return ActionResult(False, f"Application '{command.target}' was not found.", command.action, command.target)

        terminated = False
        import psutil

        expected_names = self._candidate_process_names(command.target, application_path)
        for process in psutil.process_iter(["name"]):
            process_name = (process.info.get("name") or "").lower()
            if process_name in expected_names:
                process.terminate()
                terminated = True

        message = f"Closed {command.target}." if terminated else f"No running process found for {command.target}."
        return ActionResult(terminated, message, command.action, command.target)

    def _candidate_process_names(self, target: str, application_path: str) -> set[str]:
        normalized_target = target.strip().lower().replace(" ", "")
        resolved_name = Path(application_path).stem.strip().lower()
        return {
            f"{resolved_name}.exe",
            resolved_name,
            f"{normalized_target}.exe",
            normalized_target,
        }
