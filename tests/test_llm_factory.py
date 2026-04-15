from __future__ import annotations

import pytest

from jarvis.config.strings import Strings
from jarvis.enums.llm_provider import LLMProvider
from jarvis.factories.llm_factory import LLMFactory
from jarvis.implementations.llm.fallback_llm import FallbackLLM
from jarvis.models.app_settings import AppSettings


def build_settings(provider: LLMProvider, openai_key: str = "openai-key") -> AppSettings:
    return AppSettings(
        llm_provider=provider,
        language="pt-BR",
        debug=False,
        openai_api_key=openai_key,
        gemini_api_key="gemini-key",
        anthropic_api_key="anthropic-key",
    )


def _factory(provider: LLMProvider, openai_key: str = "openai-key") -> LLMFactory:
    return LLMFactory(build_settings(provider, openai_key=openai_key), Strings("pt-BR"))


def test_llm_factory_selects_fallback() -> None:
    llm = _factory(LLMProvider.NONE).create()
    assert isinstance(llm, FallbackLLM)


def test_llm_factory_selects_gpt(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = _factory(LLMProvider.GPT)

    class FakeGPT:
        pass

    monkeypatch.setattr(factory, "_create_gpt", lambda: FakeGPT())
    assert isinstance(factory.create(), FakeGPT)


def test_llm_factory_selects_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = _factory(LLMProvider.GEMINI)

    class FakeGemini:
        pass

    monkeypatch.setattr(factory, "_create_gemini", lambda: FakeGemini())
    assert isinstance(factory.create(), FakeGemini)


def test_llm_factory_selects_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = _factory(LLMProvider.CLAUDE)

    class FakeClaude:
        pass

    monkeypatch.setattr(factory, "_create_claude", lambda: FakeClaude())
    assert isinstance(factory.create(), FakeClaude)


def test_llm_factory_falls_back_when_key_missing() -> None:
    llm = _factory(LLMProvider.GPT, openai_key="").create()
    assert isinstance(llm, FallbackLLM)
