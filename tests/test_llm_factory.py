from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.enums.llm_provider import LLMProvider
from jarvis.factories.llm_factory import LLMFactory
from jarvis.implementations.llm.fallback_llm import FallbackLLM
from jarvis.models.app_settings import AppSettings


def build_settings(provider: LLMProvider) -> AppSettings:
    return AppSettings(
        llm_provider=provider,
        openai_api_key="openai-key",
        gemini_api_key="gemini-key",
        anthropic_api_key="anthropic-key",
        asset_path=Path("assets/jarvis.png"),
        startup_audio_path=Path("speechs/good_morning.mp3"),
        success_audio_path=Path("speechs/understood.mp3"),
    )


def test_llm_factory_selects_fallback() -> None:
    llm = LLMFactory(build_settings(LLMProvider.NONE)).create()
    assert isinstance(llm, FallbackLLM)


def test_llm_factory_selects_gpt(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = LLMFactory(build_settings(LLMProvider.GPT))

    class FakeGPT:
        pass

    monkeypatch.setattr(factory, "_create_gpt", lambda: FakeGPT())
    assert isinstance(factory.create(), FakeGPT)


def test_llm_factory_selects_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = LLMFactory(build_settings(LLMProvider.GEMINI))

    class FakeGemini:
        pass

    monkeypatch.setattr(factory, "_create_gemini", lambda: FakeGemini())
    assert isinstance(factory.create(), FakeGemini)


def test_llm_factory_selects_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = LLMFactory(build_settings(LLMProvider.CLAUDE))

    class FakeClaude:
        pass

    monkeypatch.setattr(factory, "_create_claude", lambda: FakeClaude())
    assert isinstance(factory.create(), FakeClaude)


def test_llm_factory_requires_expected_key() -> None:
    settings = AppSettings(
        llm_provider=LLMProvider.GPT,
        openai_api_key="",
        gemini_api_key="gemini-key",
        anthropic_api_key="anthropic-key",
        asset_path=Path("assets/jarvis.png"),
        startup_audio_path=Path("speechs/good_morning.mp3"),
        success_audio_path=Path("speechs/understood.mp3"),
    )
    with pytest.raises(ValueError):
        LLMFactory(settings).create()
