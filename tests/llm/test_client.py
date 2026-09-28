"""Tests for the LiteLLM-backed LLMClient."""
from types import SimpleNamespace
import pytest
from unittest.mock import AsyncMock, patch

from src.llm.client import LLMClient
from src.llm.config_llm import LLMConfig


def _resp(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _chunk(content):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content))])


async def _stream_of(chunks):
    """Minimal async-iterable stand-in for litellm's streaming response."""
    for chunk in chunks:
        yield chunk


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

        # litellm's ollama/ provider appends /api/chat itself — a /v1 base 404s.
        ollama_base = ac.await_args_list[1].kwargs["api_base"]
        assert ollama_base == LLMConfig.ollama_base_url.rstrip("/")
        assert not ollama_base.endswith("/v1")


@pytest.mark.asyncio
async def test_caller_model_not_leaked_to_fallback_legs():
    """A model id is provider-specific — fallback legs use their own default."""
    with patch("src.llm.client.litellm.acompletion", new_callable=AsyncMock) as ac:
        ac.side_effect = [RuntimeError("boom"), _resp("fallback ok")]
        await LLMClient().generate("sys", "usr", provider="openai", model="gpt-4o-mini")

        assert ac.await_args_list[0].kwargs["model"] == "openai/gpt-4o-mini"
        ollama_model_arg = ac.await_args_list[1].kwargs["model"]
        assert ollama_model_arg == f"ollama/{LLMConfig.ollama_model}"
        assert "gpt-4o-mini" not in ollama_model_arg


@pytest.mark.asyncio
async def test_stream_generate_yields_deltas():
    chunks = [_chunk("he"), _chunk(None), SimpleNamespace(choices=[]), _chunk("llo")]
    with patch("src.llm.client.litellm.acompletion", new_callable=AsyncMock) as ac:
        ac.return_value = _stream_of(chunks)
        out = [token async for token in LLMClient().stream_generate("sys", "usr", provider="openai")]
        assert out == ["he", "llo"]
        assert ac.await_args.kwargs["stream"] is True


@pytest.mark.asyncio
async def test_stream_generate_falls_back_to_generate_on_failure():
    with patch("src.llm.client.litellm.acompletion", new_callable=AsyncMock) as ac:
        ac.side_effect = [RuntimeError("stream boom"), _resp("fallback text")]
        out = [token async for token in LLMClient().stream_generate("sys", "usr", provider="openai")]
        assert out == ["fallback text"]
        assert ac.await_count == 2


def test_get_available_providers_lists_all_four():
    assert set(LLMClient().get_available_providers()) == {"openai", "anthropic", "huggingface", "ollama"}


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
