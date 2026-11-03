"""Provider resolution and production licence guard for graph extraction."""

from types import SimpleNamespace

import pytest

from src.llm.config_llm import LLMConfig
from src.llm.extraction import (
    ExtractionProviderError,
    ExtractionSettings,
    assert_extraction_licensed,
    resolve_extraction_settings,
)


@pytest.fixture
def clean_extraction_env(monkeypatch):
    for name in (
        "EXTRACTION_PROVIDER",
        "EXTRACTION_BASE_URL",
        "EXTRACTION_API_KEY",
        "EXTRACTION_TRIAL_ACK",
        "EXTRACTION_LLM_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(LLMConfig, "extraction_provider", "nvidia_nim")
    monkeypatch.setattr(LLMConfig, "extraction_trial_ack", False)
    return monkeypatch


def test_default_provider_is_nvidia_nim(clean_extraction_env):
    monkeypatch = clean_extraction_env
    monkeypatch.setattr(LLMConfig, "nvidia_nim_api_key", "nim-key")
    monkeypatch.setattr(LLMConfig, "nvidia_nim_base_url", "http://nim/v1")

    settings = resolve_extraction_settings()

    assert settings.provider == "nvidia_nim"
    assert settings.base_url == "http://nim/v1"
    assert settings.api_key == "nim-key"
    assert settings.model == LLMConfig.analysis_model


def test_openrouter_resolves_its_base_and_key(clean_extraction_env):
    monkeypatch = clean_extraction_env
    monkeypatch.setenv("EXTRACTION_PROVIDER", "openrouter")
    monkeypatch.setattr(LLMConfig, "extraction_provider", "openrouter")
    monkeypatch.setattr(LLMConfig, "openrouter_api_key", "or-key")

    settings = resolve_extraction_settings()

    assert settings.provider == "openrouter"
    assert settings.base_url == "https://openrouter.ai/api/v1"
    assert settings.api_key == "or-key"


@pytest.mark.parametrize(
    "configured", ["http://localhost:11434", "http://localhost:11434/"]
)
def test_ollama_appends_v1_exactly_once(clean_extraction_env, configured):
    monkeypatch = clean_extraction_env
    monkeypatch.setattr(LLMConfig, "extraction_provider", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", configured)

    assert resolve_extraction_settings().base_url == "http://localhost:11434/v1"


def test_ollama_does_not_duplicate_existing_v1(clean_extraction_env):
    monkeypatch = clean_extraction_env
    monkeypatch.setattr(LLMConfig, "extraction_provider", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1/")

    assert resolve_extraction_settings().base_url == "http://localhost:11434/v1"


def test_prod_nim_without_ack_is_refused(clean_extraction_env, monkeypatch):
    monkeypatch.setattr(
        "src.config.settings.get_settings",
        lambda: SimpleNamespace(env="prod"),
    )
    settings = ExtractionSettings(
        provider="nvidia_nim",
        base_url="http://nim/v1",
        api_key="nim-key",
        model="m",
        trial_ack=False,
    )

    with pytest.raises(ExtractionProviderError, match="EXTRACTION_TRIAL_ACK"):
        assert_extraction_licensed(settings)


def test_prod_nim_with_ack_is_allowed(clean_extraction_env, monkeypatch):
    monkeypatch.setattr(
        "src.config.settings.get_settings",
        lambda: SimpleNamespace(env="prod"),
    )
    settings = ExtractionSettings(
        provider="nvidia_nim",
        base_url="http://nim/v1",
        api_key="nim-key",
        model="m",
        trial_ack=True,
    )

    assert_extraction_licensed(settings)  # no raise


def test_missing_key_names_the_env_var(clean_extraction_env):
    monkeypatch = clean_extraction_env
    monkeypatch.setattr(LLMConfig, "extraction_provider", "openai")
    monkeypatch.setattr(LLMConfig, "openai_api_key", None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ExtractionProviderError, match="OPENAI_API_KEY"):
        resolve_extraction_settings()


def test_unknown_provider_without_base_names_the_env_var(clean_extraction_env):
    monkeypatch = clean_extraction_env
    monkeypatch.setattr(LLMConfig, "extraction_provider", "mystery")

    with pytest.raises(ExtractionProviderError, match="EXTRACTION_BASE_URL"):
        resolve_extraction_settings()


def test_unknown_provider_uses_explicit_base(clean_extraction_env):
    monkeypatch = clean_extraction_env
    monkeypatch.setattr(LLMConfig, "extraction_provider", "mystery")
    monkeypatch.setenv("EXTRACTION_BASE_URL", "https://custom.example/v1")

    settings = resolve_extraction_settings()

    assert settings.base_url == "https://custom.example/v1"
    assert settings.api_key == "not-needed"
