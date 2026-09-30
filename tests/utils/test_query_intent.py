"""Unit tests for S3 query intent extraction (src/utils/queryIntend.py).

The LiteLLM client is stubbed here — no test in this file touches a provider.
"""
import inspect
import json

import pytest

from src.llm.config_llm import get_llm_config
from src.utils import queryIntend as qi

QUERY = "Should the company expand into the European market?"

LLM_JSON = json.dumps({
    "core_question": "Should the company expand into Europe?",
    "domain_tags": ["economic", "legal"],
    "direct_keywords": ["expansion", "Europe"],
    "latent_sectors": ["logistics"],
    "entity_frame": ["European Union"],
    "search_perspectives": ["Economic", "Legal"],
    "stance_axis": "support = favouring European expansion",
})

INTENT_FIELDS = {
    "core_question",
    "domain_tags",
    "direct_keywords",
    "latent_sectors",
    "entity_frame",
    "search_perspectives",
    "stance_axis",
    "extraction_confidence",
    "llm_model",
    "llm_provider",
}


class StubClient:
    """Stand-in for LLMClient that records the calls it receives."""

    def __init__(self, reply: str = "", error: Exception | None = None):
        self.reply = reply
        self.error = error
        self.calls: list[dict] = []

    async def generate(self, system_prompt, user_prompt, provider=None, model=None, temperature=None):
        self.calls.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "provider": provider,
            "model": model,
            "temperature": temperature,
        })
        if self.error:
            raise self.error
        return self.reply


def _extractor(stub: StubClient, **kwargs) -> qi.QueryIntend:
    return qi.QueryIntend(model="test-model", provider="openai", client=stub, **kwargs)


@pytest.mark.asyncio
async def test_expand_user_query_awaits_client_and_parses_llm_fields():
    stub = StubClient(reply=LLM_JSON)

    intent = await _extractor(stub).expand_user_query(QUERY)

    # Stub only records a call when its coroutine actually ran (i.e. was awaited).
    assert len(stub.calls) == 1
    assert QUERY in stub.calls[0]["user_prompt"]
    assert stub.calls[0]["model"] == "test-model"
    assert stub.calls[0]["provider"] == "openai"

    assert intent.core_question == "Should the company expand into Europe?"
    assert intent.domain_tags == ["economic", "legal"]
    assert intent.direct_keywords == ["expansion", "Europe"]
    assert intent.latent_sectors == ["logistics"]
    assert intent.entity_frame == ["European Union"]
    assert intent.search_perspectives == ["Economic", "Legal"]
    assert intent.stance_axis == "support = favouring European expansion"
    assert intent.extraction_confidence == qi.LLM_EXTRACTION_CONFIDENCE
    assert (intent.llm_model, intent.llm_provider) == ("test-model", "openai")


@pytest.mark.asyncio
async def test_expand_user_query_parses_json_wrapped_in_fences():
    stub = StubClient(reply=f"```json\n{LLM_JSON}\n```")

    intent = await _extractor(stub).expand_user_query(QUERY)

    assert intent.extraction_confidence == qi.LLM_EXTRACTION_CONFIDENCE
    assert intent.core_question == "Should the company expand into Europe?"


@pytest.mark.asyncio
async def test_llm_failure_returns_deterministic_fallback(caplog):
    stub = StubClient(error=RuntimeError("provider down"))

    intent = await _extractor(stub).expand_user_query(QUERY, selected_domains=["legal", "economic"])

    assert intent.core_question == QUERY
    assert intent.domain_tags == ["legal", "economic"]
    assert intent.direct_keywords == [QUERY]
    assert intent.latent_sectors == []
    assert intent.entity_frame == []
    assert intent.stance_axis == ""
    assert intent.extraction_confidence == qi.FALLBACK_EXTRACTION_CONFIDENCE
    assert intent.extraction_confidence < qi.LLM_EXTRACTION_CONFIDENCE
    assert (intent.llm_model, intent.llm_provider) == ("test-model", "openai")
    assert any("fallback" in record.getMessage().lower() for record in caplog.records)


@pytest.mark.asyncio
async def test_unparseable_reply_returns_deterministic_fallback():
    stub = StubClient(reply="I'm sorry, I can't help with that.")

    intent = await _extractor(stub).expand_user_query(QUERY, selected_domains=["legal"])

    assert intent.extraction_confidence == qi.FALLBACK_EXTRACTION_CONFIDENCE
    assert intent.core_question == QUERY
    assert intent.domain_tags == ["legal"]


@pytest.mark.asyncio
async def test_blank_query_returns_none_without_calling_the_llm():
    stub = StubClient(reply=LLM_JSON)

    assert await _extractor(stub).expand_user_query("   ") is None
    assert stub.calls == []


def test_intent_is_constructible_without_llm_and_serializes_round_trip():
    intent = qi.QueryIntent(
        direct_keywords=["expansion"],
        latent_sectors=[],
        search_perspectives=["Economic"],
    )

    dumped = intent.model_dump()

    assert set(dumped) == INTENT_FIELDS
    assert json.loads(json.dumps(dumped)) == dumped
    assert qi.QueryIntent.model_validate(dumped) == intent


def test_fallback_intent_serializes_round_trip():
    intent = _extractor(StubClient()).fallback_intent(QUERY, ["legal"])

    dumped = intent.model_dump()

    assert set(dumped) == INTENT_FIELDS
    assert qi.QueryIntent.model_validate(json.loads(json.dumps(dumped))) == intent


def test_model_defaults_to_configuration():
    extractor = qi.QueryIntend(client=StubClient())

    config = get_llm_config()

    assert extractor.provider == config.default_llm_provider
    assert extractor.model == getattr(config, f"{config.default_llm_provider}_model")
    assert extractor.model


def test_module_has_no_blocking_call_and_no_hardcoded_model():
    source = inspect.getsource(qi)

    assert "ChatOllama" not in source
    assert ".invoke(" not in source
    assert "gemma4" not in source
