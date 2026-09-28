"""Tests for the LiteLLM-backed LLMClient."""
from types import SimpleNamespace
import pytest
from unittest.mock import AsyncMock, patch

from src.llm.client import LLMClient


def _resp(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


@pytest.mark.asyncio
async def test_generate_returns_content():
    with patch("src.llm.client.litellm.acompletion", new_callable=AsyncMock) as ac:
        ac.return_value = _resp("hello")
        out = await LLMClient().generate("sys", "usr", provider="openai")
        assert out == "hello"
        assert ac.await_args.kwargs["model"].startswith("openai/")


@pytest.mark.asyncio
async def test_generate_falls_back_on_provider_failure():
    with patch("src.llm.client.litellm.acompletion", new_callable=AsyncMock) as ac:
        ac.side_effect = [RuntimeError("boom"), _resp("fallback ok")]
        out = await LLMClient().generate("sys", "usr", provider="openai")
        assert out == "fallback ok"
        assert ac.await_count == 2
        chain_first, chain_second = ac.await_args_list[0].kwargs["model"], ac.await_args_list[1].kwargs["model"]
        assert chain_first.startswith("openai/") and chain_second.startswith("ollama/")


@pytest.mark.asyncio
async def test_generate_raises_when_all_fail():
    with patch("src.llm.client.litellm.acompletion", new_callable=AsyncMock) as ac:
        ac.side_effect = RuntimeError("boom")
        with pytest.raises(RuntimeError, match="All LLM providers failed"):
            await LLMClient().generate("sys", "usr", provider="openai")


def test_unknown_provider_rejected():
    with pytest.raises(ValueError, match="Unknown provider"):
        import asyncio
        asyncio.run(LLMClient().generate("s", "u", provider="nope"))
