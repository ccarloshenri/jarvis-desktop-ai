from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus

from jarvis.enums.action_type import ActionType
from jarvis.interfaces.iaction_executor import IActionExecutor
from jarvis.interfaces.iapplication_finder import IApplicationFinder
from jarvis.interfaces.ispotify_controller import ISpotifyController
from jarvis.models.action_result import ActionResult
from jarvis.models.command import Command


class SystemActionExecutor(IActionExecutor):
    def __init__(
        self,
        application_finder: IApplicationFinder,
        spotify_controller: ISpotifyController | None = None,
    ) -> None:
        self._application_finder = application_finder
        self._spotify_controller = spotify_controller

    def execute(self, command: Command) -> ActionResult:
        if command.action == ActionType.OPEN_APP:
            return self._open_application(command)
        if command.action == ActionType.CLOSE_APP:
            return self._close_application(command)
        if command.action == ActionType.PLAY_SPOTIFY:
            return self._play_spotify(command)
        if command.action == ActionType.SEARCH_WEB:
            return self._search_web(command)
        raise ValueError(f"Unsupported action '{command.action.value}'.")

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
