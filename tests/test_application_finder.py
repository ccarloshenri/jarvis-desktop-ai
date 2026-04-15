from __future__ import annotations

from pathlib import Path

from jarvis.implementations.system.application_cache import ApplicationCache
from jarvis.implementations.system.windows_application_finder import WindowsApplicationFinder
from jarvis.models.application_candidate import ApplicationCandidate


class StubFinder(WindowsApplicationFinder):
    def __init__(self, candidates: list[ApplicationCandidate], cache: ApplicationCache | None = None) -> None:
        super().__init__(
            cache=cache,
            common_start_menu=Path("unused"),
            user_start_menu=Path("unused"),
        )
        self._stub_candidates = candidates
        self.scan_count = 0

    def _scan_root(self, root: Path) -> list[ApplicationCandidate]:
        self.scan_count += 1
        return list(self._stub_candidates)


def test_finder_prefers_exact_match() -> None:
    finder = StubFinder(
        [
            ApplicationCandidate("Steam", Path(r"C:\Apps\Steam\Steam.exe")),
            ApplicationCandidate("Steam Setup", Path(r"C:\Downloads\SteamSetup.exe")),
        ]
    )
    assert finder.find("steam") == r"C:\Apps\Steam\Steam.exe"


def test_finder_supports_partial_and_fuzzy_matching() -> None:
    finder = StubFinder(
        [
            ApplicationCandidate("Visual Studio Code", Path(r"C:\Apps\VS Code\Code.exe")),
            ApplicationCandidate("Video Studio", Path(r"C:\Apps\VideoStudio.exe")),
        ]
    )
    assert finder.find("visual studio") == r"C:\Apps\VS Code\Code.exe"


def test_finder_supports_alias_normalization() -> None:
    finder = StubFinder([ApplicationCandidate("Visual Studio Code", Path(r"C:\Apps\VS Code\Code.exe"))])
    assert finder.find("vscode") == r"C:\Apps\VS Code\Code.exe"


def test_finder_caches_scan_results() -> None:
    cache = ApplicationCache()
    finder = StubFinder([ApplicationCandidate("Steam", Path(r"C:\Apps\Steam\Steam.exe"))], cache=cache)
    assert finder.find("steam") == r"C:\Apps\Steam\Steam.exe"
    assert finder.find("steam") == r"C:\Apps\Steam\Steam.exe"
    assert finder.scan_count == 2


def test_finder_returns_none_when_no_match_exists() -> None:
    finder = StubFinder([ApplicationCandidate("Discord", Path(r"C:\Apps\Discord.exe"))])
    assert finder.find("steam") is None
