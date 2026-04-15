from __future__ import annotations

from pathlib import Path

from jarvis.enums.llm_provider import LLMProvider
from jarvis.services.provider_config import ProviderConfig


def test_provider_config_round_trip(tmp_path: Path) -> None:
    config = ProviderConfig(path=tmp_path / "config.json")
    assert config.load_active_provider() is None

    config.save_active_provider(LLMProvider.GPT)
    assert config.load_active_provider() == LLMProvider.GPT

    config.save_active_provider(LLMProvider.GEMINI)
    assert config.load_active_provider() == LLMProvider.GEMINI


def test_provider_config_clear(tmp_path: Path) -> None:
    config = ProviderConfig(path=tmp_path / "config.json")
    config.save_active_provider(LLMProvider.CLAUDE)
    config.clear()
    assert config.load_active_provider() is None


def test_provider_config_creates_parent_dirs(tmp_path: Path) -> None:
    config = ProviderConfig(path=tmp_path / "nested" / "dir" / "config.json")
    config.save_active_provider(LLMProvider.NONE)
    assert config.load_active_provider() == LLMProvider.NONE


def test_provider_config_ignores_invalid_value(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"active_provider": "nonsense"}', encoding="utf-8")
    config = ProviderConfig(path=path)
    assert config.load_active_provider() is None


def test_provider_config_handles_missing_file(tmp_path: Path) -> None:
    config = ProviderConfig(path=tmp_path / "never_created.json")
    assert config.load_active_provider() is None
