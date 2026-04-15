from __future__ import annotations

import subprocess
from pathlib import Path

from jarvis.enums.action_type import ActionType
from jarvis.interfaces.iaction_executor import IActionExecutor
from jarvis.interfaces.iapplication_finder import IApplicationFinder
from jarvis.models.action_result import ActionResult
from jarvis.models.command import Command


class SystemActionExecutor(IActionExecutor):
    def __init__(self, application_finder: IApplicationFinder) -> None:
        self._application_finder = application_finder

    def execute(self, command: Command) -> ActionResult:
        if command.action == ActionType.OPEN_APP:
            return self._open_application(command)
        if command.action == ActionType.CLOSE_APP:
            return self._close_application(command)
        raise ValueError(f"Unsupported action '{command.action.value}'.")

    def _open_application(self, command: Command) -> ActionResult:
        application_path = self._application_finder.find(command.target)
        if application_path is None:
            return ActionResult(False, f"Application '{command.target}' was not found.", command.action, command.target)
        try:
            subprocess.Popen(application_path)
            return ActionResult(True, f"Opened {command.target}.", command.action, command.target)
        except OSError as exc:
            return ActionResult(False, str(exc), command.action, command.target)

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
