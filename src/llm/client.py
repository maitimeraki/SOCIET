"""Unified LLM client — LiteLLM gateway (one interface, 100+ providers).

Public surface unchanged for all callers:
    await llm.generate(system_prompt, user_prompt, provider=..., model=..., temperature=...) -> str
    async for token in llm.stream_generate(system_prompt, user_prompt, provider=..., model=...)
    llm.get_available_providers() -> dict
Fallback chain: requested provider first, then the configured ``LLM_FALLBACK_CHAIN``.
"""

import asyncio
import logging
import os
import uuid
from collections.abc import Mapping
from types import SimpleNamespace
from typing import AsyncGenerator, Optional

import litellm

from src.billing import metering
from src.config.settings import get_settings
from src.llm.config_llm import LLMConfig

logger = logging.getLogger(__name__)

# Every LLM attempt is explicitly bounded (litellm's default attempt timeout is 6000 s).
LLM_ATTEMPT_TIMEOUT_SECONDS = 90  # per HTTP attempt
LLM_NUM_RETRIES = 1  # litellm-level retries per fallback leg
LLM_TOTAL_DEADLINE_SECONDS = 300  # the whole fallback chain, all legs together


def _fallback_order() -> list[str]:
    """Configured fallback providers.

    Billing means the subprocessor is named in the privacy policy, so with
    billing enabled and no explicit chain we never silently switch providers.
    """
    if not os.getenv("LLM_FALLBACK_CHAIN") and get_settings().billing_enabled:
        return []
    return [p.strip() for p in LLMConfig.fallback_chain.split(",") if p.strip()]


def _messages(provider: str, system_prompt: str, user_prompt: str) -> list[dict]:
    """System message shape for the serving provider (prompt caching, R22)."""
    content = system_prompt
    if provider == "anthropic" and getattr(LLMConfig, "prompt_cache", True):
        content = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]
    return [
        {"role": "system", "content": content},
        {"role": "user", "content": user_prompt},
    ]


class LLMClient:
    """Multi-provider LLM client over the LiteLLM gateway."""

    PROVIDERS = [
        "openai",
        "anthropic",
        "huggingface",
        "ollama",
        "openrouter",
        "deepseek",
        "sarvam",
        "minimax",
    ]
    @staticmethod
    def _model_str(provider: str, model: Optional[str]) -> str:
        if provider == "ollama":
            return f"ollama/{model or getattr(LLMConfig, 'ollama_model', 'qwen3.5-16k:4b')}"
        if provider == "huggingface":
            return f"huggingface/{model or getattr(LLMConfig, 'huggingface_model', 'Qwen/Qwen3.5-9B')}"
        if provider == "openai":
            return (
                f"openai/{model or getattr(LLMConfig, 'openai_model', 'gpt-3.5-turbo')}"
            )
        return f"{provider}/{model or getattr(LLMConfig, 'anthropic_model', 'claude-sonnet-4-5')}"

    @staticmethod
    def _call_kwargs(provider: str) -> dict:
        kwargs: dict = {}
        if provider == "ollama":
            # litellm's ollama/ provider speaks Ollama's native API and appends
            # /api/chat itself, so it needs the bare base — a /v1 suffix 404s.
            base = getattr(LLMConfig, "ollama_base_url", "http://localhost:11434")
            kwargs["api_base"] = base.rstrip("/")
            kwargs["api_key"] = "ollama"
            # The Ollama leg forwards BOTH max_tokens and num_predict; litellm's
            # native ollama/ provider may reject the pair. drop_params makes
            # litellm silently drop the unsupported one instead of raising, so
            # the default local provider never fails on the kwarg mismatch.
            kwargs["drop_params"] = True
        elif provider == "openai" and LLMConfig.openai_api_key:
            kwargs["api_key"] = LLMConfig.openai_api_key
        elif provider == "anthropic" and LLMConfig.anthropic_api_key:
            kwargs["api_key"] = LLMConfig.anthropic_api_key
        elif provider == "huggingface" and LLMConfig.huggingface_api_key:
            os.environ.setdefault("HF_TOKEN", LLMConfig.huggingface_api_key)
        elif provider == "openrouter" and LLMConfig.nvidia_nim_api_key:
            kwargs["api_key"] = LLMConfig.nvidia_nim_api_key
            kwargs["api_base"] = LLMConfig.nvidia_nim_base_url
        elif provider == "deepseek" and LLMConfig.nvidia_nim_api_key:
            conversation_session_id = str(uuid.uuid4())
            kwargs["api_key"] = LLMConfig.nvidia_nim_api_key
            kwargs["api_base"] = LLMConfig.nvidia_nim_base_url
            kwargs["extra_headers"] = {"x-opencode-session": conversation_session_id}
            kwargs["drop_params"] = True
        return kwargs

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate a completion. Falls back through the provider chain on failure."""
        metering.check_metering()
        provider = provider or getattr(LLMConfig, "default_llm_provider", "ollama")
        # LLMClient is the debate stack: with no model named, use the debate tier.
        model = model or LLMConfig.debate_model
        if provider not in self.PROVIDERS:
            raise ValueError(
                f"Unknown provider: {provider}. Available: {self.PROVIDERS}"
            )

        chain = [provider] + [p for p in _fallback_order() if p != provider]
        errors: list[str] = []
        output_cap = (
            max_tokens
            if max_tokens is not None
            else getattr(LLMConfig, "max_output_tokens", 2048)
        )

        async def _run_chain() -> str:
            for p in chain:
                try:
                    # The caller's model id is only meaningful for the provider they
                    # named; a fallback leg must use its own configured model.
                    leg_model = model if p == provider else None
                    kwargs = self._call_kwargs(p)
                    kwargs["max_tokens"] = output_cap
                    if p == "ollama":
                        # Ollama's native API names the output cap num_predict.
                        kwargs["num_predict"] = output_cap
                    response = await litellm.acompletion(
                        model=self._model_str(p, leg_model),
                        messages=_messages(p, system_prompt, user_prompt),
                        temperature=0.7 if temperature is None else temperature,
                        timeout=LLM_ATTEMPT_TIMEOUT_SECONDS,
                        num_retries=LLM_NUM_RETRIES,
                        **kwargs,
                    )
                    if metering.current_context() is not None:
                        await metering.record_response(
                            response,
                            provider=p,
                            fallback_model=self._model_str(p, leg_model),
                        )
                    return response.choices[0].message.content or ""
                except Exception as exc:
                    errors.append(f"{p}: {exc}")
                    logger.warning("LLM provider %s failed: %s", p, exc)
            raise RuntimeError("All LLM providers failed: " + "; ".join(errors))

        try:
            return await asyncio.wait_for(
                _run_chain(), timeout=LLM_TOTAL_DEADLINE_SECONDS
            )
        except asyncio.TimeoutError:
            detail = (
                f"LLM call exceeded total deadline of {LLM_TOTAL_DEADLINE_SECONDS}s"
            )
            if errors:
                detail += " after: " + "; ".join(errors)
            raise RuntimeError(detail)

    async def stream_generate(
        self,
        system_prompt: str,
        user_prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens; degrades to a single generate() call on failure."""
        metering.check_metering()
        provider = provider or getattr(LLMConfig, "default_llm_provider", "ollama")
        model = model or LLMConfig.debate_model
        if provider not in self.PROVIDERS:
            raise ValueError(
                f"Unknown provider: {provider}. Available: {self.PROVIDERS}"
            )
        last_usage = None
        last_model = None
        last_hidden = None
        try:
            response = await litellm.acompletion(
                model=self._model_str(provider, model),
                messages=_messages(provider, system_prompt, user_prompt),
                temperature=0.7,
                stream=True,
                timeout=LLM_ATTEMPT_TIMEOUT_SECONDS,
                **self._call_kwargs(provider),
            )
            async for chunk in response:
                usage = getattr(chunk, "usage", None)
                if usage is not None:
                    last_usage = usage
                    last_model = getattr(chunk, "model", None) or last_model
                    hidden = getattr(chunk, "_hidden_params", None)
                    if isinstance(hidden, Mapping):
                        last_hidden = hidden
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield str(delta)
        except Exception as exc:
            logger.warning(
                "Streaming failed for %s: %s — falling back to generate()",
                provider,
                exc,
            )
            # generate() meters its own call — never record this stream too.
            yield await self.generate(
                system_prompt, user_prompt, provider=provider, model=model
            )
            return
        await metering.record_response(
            SimpleNamespace(
                usage=last_usage, model=last_model, _hidden_params=last_hidden or {}
            ),
            provider=provider,
            fallback_model=self._model_str(provider, model),
        )

    def get_available_providers(self) -> dict:
        """Which providers are configured/reachable."""
        return {
            "openai": bool(LLMConfig.openai_api_key),
            "anthropic": bool(LLMConfig.anthropic_api_key),
            "huggingface": bool(LLMConfig.huggingface_api_key),
            "ollama": self._check_ollama_available(),
        }

    @staticmethod
    def _check_ollama_available() -> bool:
        try:
            import requests

            base = getattr(LLMConfig, "ollama_base_url", "http://localhost:11434")
            response = requests.get(f"{base}/api/tags", timeout=2)
            return response.status_code == 200
        except Exception:
            return False


# Global singleton for reuse
global_llm_client = LLMClient()
