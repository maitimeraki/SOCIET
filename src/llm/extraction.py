"""One env-driven provider for the graph extraction stages (plan §2 B0/B3).

The graph stages construct ``OpenAILike`` directly, so their provider must be
resolved here rather than in ``LLMClient``. Defaults stay on NVIDIA NIM for
dev; production refuses that catalog unless the operator acknowledges the
trial licence.
"""

import os
from dataclasses import dataclass

from src.llm.config_llm import LLMConfig

_NIM_BASE = "https://integrate.api.nvidia.com/v1"
_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_OPENAI_BASE = "https://api.openai.com/v1"
_DEEPINFRA_BASE = "https://api.deepinfra.com/v1/openai"
_LOCALAI_BASE = "http://localhost:8080/v1"


@dataclass(frozen=True)
class ExtractionSettings:
    provider: str
    base_url: str
    api_key: str
    model: str
    trial_ack: bool


class ExtractionProviderError(RuntimeError):
    """The configured extraction provider cannot be used as-is."""


def _env(name: str) -> str:
    return os.getenv(name, "")


def _provider() -> str:
    return _env("EXTRACTION_PROVIDER") or getattr(
        LLMConfig, "extraction_provider", "nvidia_nim"
    )


def _trial_ack() -> bool:
    raw = os.getenv("EXTRACTION_TRIAL_ACK")
    if raw is None:
        return bool(getattr(LLMConfig, "extraction_trial_ack", False))
    return raw.lower() in ("1", "true", "yes")


def _missing(env_vars: str) -> ExtractionProviderError:
    return ExtractionProviderError(
        f"extraction provider configuration is incomplete: set {env_vars}"
    )


def _ollama_base() -> str:
    base = (
        _env("EXTRACTION_BASE_URL")
        or _env("OLLAMA_BASE_URL")
        or getattr(LLMConfig, "ollama_base_url", "")
        or "http://localhost:11434"
    ).rstrip("/")
    return base if base.endswith("/v1") else f"{base}/v1"


def resolve_extraction_settings(model: str | None = None) -> ExtractionSettings:
    """Resolve provider, base URL, key and model from the environment."""
    provider = _provider()
    base_override = _env("EXTRACTION_BASE_URL")
    key_override = _env("EXTRACTION_API_KEY")

    if provider == "nvidia_nim":
        base_url = (
            base_override
            or getattr(LLMConfig, "nvidia_nim_base_url", "")
            or _NIM_BASE
        )
        api_key = key_override or getattr(LLMConfig, "nvidia_nim_api_key", "")
        if not api_key:
            raise _missing("EXTRACTION_API_KEY (or NVIDIA_NIM_API_KEY)")
    elif provider == "openrouter":
        base_url = base_override or _OPENROUTER_BASE
        api_key = key_override or getattr(LLMConfig, "openrouter_api_key", "")
        if not api_key:
            raise _missing("EXTRACTION_API_KEY (or OPENROUTER_API_KEY)")
    elif provider == "openai":
        base_url = base_override or _OPENAI_BASE
        api_key = key_override or getattr(LLMConfig, "openai_api_key", "")
        if not api_key:
            raise _missing("EXTRACTION_API_KEY (or OPENAI_API_KEY)")
    elif provider == "deepinfra":
        base_url = base_override or _DEEPINFRA_BASE
        api_key = key_override
        if not api_key:
            raise _missing("EXTRACTION_API_KEY")
    elif provider == "ollama":
        base_url = _ollama_base()
        api_key = "ollama"
    elif provider == "localai":
        base_url = (
            base_override
            or _env("LOCALAI_BASE_URL")
            or _LOCALAI_BASE
        )
        api_key = key_override or "local"
    else:
        base_url = base_override
        if not base_url:
            raise _missing("EXTRACTION_BASE_URL")
        api_key = key_override or "not-needed"

    resolved_model = model or getattr(LLMConfig, "extraction_model", "")
    if not resolved_model:
        raise _missing("EXTRACTION_LLM_MODEL (or ANALYSIS_LLM_MODEL)")

    return ExtractionSettings(
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        model=resolved_model,
        trial_ack=_trial_ack(),
    )


def assert_extraction_licensed(settings: ExtractionSettings) -> None:
    """Refuse the free NVIDIA NIM catalog for end users in production."""
    from src.config.settings import get_settings

    if (
        get_settings().env == "prod"
        and settings.provider == "nvidia_nim"
        and not settings.trial_ack
    ):
        raise ExtractionProviderError(
            "NVIDIA NIM's free catalog is licensed for prototyping only and must "
            "not serve end users. Set EXTRACTION_PROVIDER to a licensed or "
            "partner endpoint, or set EXTRACTION_TRIAL_ACK=true after purchasing "
            "a licence."
        )
