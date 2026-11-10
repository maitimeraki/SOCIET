"""The OpenAILike metering wrapper for the graph extraction path (R25)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.graph.llm_metering import wrap_with_metering


class _FakeResponse:
    def __init__(self):
        self.raw = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=1500, completion_tokens=500)
        )
        self.additional_kwargs = {}


class _FakeLLM:
    def __init__(self):
        self.response = _FakeResponse()
        self.calls = []

    async def _achat(self, messages, **kwargs):
        self.calls.append(("_achat", messages, kwargs))
        return self.response

    async def _acomplete(self, prompt, **kwargs):
        self.calls.append(("_acomplete", prompt, kwargs))
        return self.response


@pytest.mark.asyncio
async def test_wrapped_methods_record_once_and_return_the_response():
    llm = _FakeLLM()

    with patch(
        "src.billing.metering.record_llama_response", new_callable=AsyncMock
    ) as record:
        wrap_with_metering(llm, provider="nvidia_nim", model="nit-model")
        chat = await llm._achat("chat")
        complete = await llm._acomplete("complete")

    assert chat is llm.response
    assert complete is llm.response
    assert llm.calls == [
        ("_achat", "chat", {}),
        ("_acomplete", "complete", {}),
    ]
    assert record.await_count == 2
    for call in record.await_args_list:
        assert call.kwargs == {"provider": "nvidia_nim", "model": "nit-model"}


@pytest.mark.asyncio
async def test_wrapping_twice_does_not_double_record():
    llm = _FakeLLM()

    with patch(
        "src.billing.metering.record_llama_response", new_callable=AsyncMock
    ) as record:
        wrap_with_metering(llm, provider="nvidia_nim", model="m")
        wrap_with_metering(llm, provider="nvidia_nim", model="m")
        await llm._achat("chat")

    assert record.await_count == 1


def test_object_without_methods_is_returned_unchanged():
    llm = SimpleNamespace()

    assert wrap_with_metering(llm, provider="ollama", model="m") is llm


@pytest.mark.asyncio
async def test_flagged_context_stops_the_call_before_it_spends():
    """Fail closed: a prior settlement failure raises before the original call."""
    import datetime
    import uuid

    from src.billing import metering

    llm = _FakeLLM()
    wrap_with_metering(llm, provider="nvidia_nim", model="m")

    with metering.metering_scope(
        user_id=uuid.uuid4(),
        period_start=datetime.datetime.now(datetime.UTC),
        source="ontology",
    ) as context:
        context.failed = True
        context.failure_reason = "settlement failed"
        with pytest.raises(metering.MeteringError):
            await llm._achat("chat")

    assert llm.calls == []
