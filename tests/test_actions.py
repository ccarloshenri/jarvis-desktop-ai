from __future__ import annotations

from jarvis.enums.action_type import ActionType
from jarvis.implementations.system.system_action_executor import SystemActionExecutor
from jarvis.models.command import Command


class FakeApplicationFinder:
    def __init__(self, path: str | None) -> None:
        self._path = path

    def find(self, name: str) -> str | None:
        return self._path


class FakeProcess:
    def __init__(self, name: str) -> None:
        self.info = {"name": name}
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True


def test_action_executor_opens_registered_application(monkeypatch) -> None:
    executor = SystemActionExecutor(FakeApplicationFinder(r"C:\Apps\Notepad\Notepad.exe"))
    launched = {}

    def fake_popen(command, **kwargs):
        launched["command"] = command
        return object()

    monkeypatch.setattr("jarvis.implementations.system.system_action_executor.subprocess.Popen", fake_popen)
    result = executor.execute(Command(action=ActionType.OPEN_APP, target="notepad"))

    assert result.success is True
    assert launched["command"] == [r"C:\Apps\Notepad\Notepad.exe"]


def test_action_executor_fails_for_unknown_application() -> None:
    executor = SystemActionExecutor(FakeApplicationFinder(None))
    result = executor.execute(Command(action=ActionType.OPEN_APP, target="unknown"))
    assert result.success is False


def test_action_executor_closes_matching_processes(monkeypatch) -> None:
    executor = SystemActionExecutor(FakeApplicationFinder(r"C:\Users\carlo\AppData\Local\Programs\Steam\Steam.exe"))
    processes = [FakeProcess("steam.exe"), FakeProcess("other.exe")]

    class FakePsutil:
        def process_iter(self, fields):
            return processes

    monkeypatch.setitem(__import__("sys").modules, "psutil", FakePsutil())
    result = executor.execute(Command(action=ActionType.CLOSE_APP, target="steam"))

    assert result.success is True
    assert processes[0].terminated is True
    assert processes[1].terminated is False
