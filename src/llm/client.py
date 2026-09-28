"""Unified LLM client — LiteLLM gateway (one interface, 100+ providers).

Public surface unchanged for all callers:
    await llm.generate(system_prompt, user_prompt, provider=..., model=..., temperature=...) -> str
    async for token in llm.stream_generate(system_prompt, user_prompt, provider=..., model=...)
    llm.get_available_providers() -> dict
Fallback chain: requested provider first, then ollama -> openai -> anthropic -> huggingface.
"""
import logging
import os
from typing import AsyncGenerator, Optional

import litellm

from src.llm.config_llm import LLMConfig

logger = logging.getLogger(__name__)


class LLMClient:
    """Multi-provider LLM client over the LiteLLM gateway."""

    PROVIDERS = ["openai", "anthropic", "huggingface", "ollama"]
    FALLBACK_ORDER = ["ollama", "openai", "anthropic", "huggingface"]

    @staticmethod
    def _model_str(provider: str, model: Optional[str]) -> str:
        if provider == "ollama":
            return f"ollama/{model or getattr(LLMConfig, 'ollama_model', 'qwen3.5:4b')}"
        if provider == "huggingface":
            return f"huggingface/{model or getattr(LLMConfig, 'huggingface_model', 'Qwen/Qwen3.5-9B')}"
        if provider == "openai":
            return f"openai/{model or getattr(LLMConfig, 'openai_model', 'gpt-3.5-turbo')}"
        return f"{provider}/{model or getattr(LLMConfig, 'anthropic_model', 'claude-sonnet-4-5')}"

    @staticmethod
    def _call_kwargs(provider: str) -> dict:
        kwargs: dict = {}
        if provider == "ollama":
            base = getattr(LLMConfig, "ollama_base_url", "http://localhost:11434")
            kwargs["api_base"] = f"{base.rstrip('/')}/v1"
            kwargs["api_key"] = "ollama"
        elif provider == "openai" and LLMConfig.openai_api_key:
            kwargs["api_key"] = LLMConfig.openai_api_key
        elif provider == "anthropic" and LLMConfig.anthropic_api_key:
            kwargs["api_key"] = LLMConfig.anthropic_api_key
        elif provider == "huggingface" and LLMConfig.huggingface_api_key:
            os.environ.setdefault("HF_TOKEN", LLMConfig.huggingface_api_key)
        return kwargs

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """Generate a completion. Falls back through the provider chain on failure."""
        provider = provider or getattr(LLMConfig, "default_llm_provider", "ollama")
        if provider not in self.PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}. Available: {self.PROVIDERS}")

        chain = [provider] + [p for p in self.FALLBACK_ORDER if p != provider]
        errors: list[str] = []
        for p in chain:
            try:
                response = await litellm.acompletion(
                    model=self._model_str(p, model),
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.7 if temperature is None else temperature,
                    num_retries=2,
                    **self._call_kwargs(p),
                )
                return response.choices[0].message.content or ""
            except Exception as exc:
                errors.append(f"{p}: {exc}")
                logger.warning("LLM provider %s failed: %s", p, exc)
        raise RuntimeError("All LLM providers failed: " + "; ".join(errors))

    async def stream_generate(
        self,
        system_prompt: str,
        user_prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens; degrades to a single generate() call on failure."""
        provider = provider or getattr(LLMConfig, "default_llm_provider", "ollama")
        if provider not in self.PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}. Available: {self.PROVIDERS}")
        try:
            response = await litellm.acompletion(
                model=self._model_str(provider, model),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                stream=True,
                **self._call_kwargs(provider),
            )
            async for chunk in response:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield str(delta)
        except Exception as exc:
            logger.warning("Streaming failed for %s: %s — falling back to generate()", provider, exc)
            yield await self.generate(system_prompt, user_prompt, provider=provider, model=model)

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
