import pytest

from src.billing.metering import MeteringError
from src.llm.config_llm import get_llm_config
from src.simulation.actor_filter import classify_actor_labels


class FakeClient:
    def __init__(self, reply: str = "", raises: Exception | None = None):
        self.reply = reply
        self.raises = raises
        self.calls = 0
        self.kwargs: dict = {}

    async def generate(self, **kwargs) -> str:
        self.calls += 1
        self.kwargs = kwargs
        if self.raises is not None:
            raise self.raises
        return self.reply


@pytest.mark.asyncio
async def test_labels_are_classified_in_one_call():
    client = FakeClient('{"Company": true, "Revenue": false}')
    result, degraded = await classify_actor_labels(client, ["Company", "Revenue"])
    assert result == {"Company": True, "Revenue": False} and not degraded and client.calls == 1


@pytest.mark.asyncio
async def test_failure_treats_every_label_as_an_actor_and_flags_it():
    result, degraded = await classify_actor_labels(
        FakeClient(raises=RuntimeError("down")), ["Company", "Revenue"]
    )
    assert result == {"Company": True, "Revenue": True} and degraded


@pytest.mark.asyncio
async def test_metering_errors_are_not_absorbed():
    with pytest.raises(MeteringError):
        await classify_actor_labels(FakeClient(raises=MeteringError("hold gone")), ["Company"])


@pytest.mark.asyncio
async def test_a_label_missing_from_the_reply_is_treated_as_an_actor_and_flagged():
    result, degraded = await classify_actor_labels(
        FakeClient('{"Company": true}'), ["Company", "Revenue"]
    )
    assert result["Revenue"] is True and degraded


@pytest.mark.asyncio
async def test_empty_labels_make_no_call_and_are_not_degraded():
    client = FakeClient('{}')
    result, degraded = await classify_actor_labels(client, [])
    assert result == {} and not degraded and client.calls == 0


@pytest.mark.asyncio
async def test_call_is_deterministic_with_explicit_budget_and_model():
    client = FakeClient('{"Company": true}')
    await classify_actor_labels(client, ["Company"])
    assert (
        client.kwargs["temperature"] == 0
        and client.kwargs["max_tokens"] == 400
        and client.kwargs["model"] == get_llm_config().analysis_model
    )


@pytest.mark.asyncio
async def test_output_budget_scales_with_label_count():
    labels = [f"Label{i}" for i in range(60)]
    client = FakeClient("{}")
    await classify_actor_labels(client, labels)
    assert client.kwargs["max_tokens"] >= 25 * 60


@pytest.mark.asyncio
async def test_system_prompt_marks_the_labels_as_data_not_instructions():
    client = FakeClient('{"Company": true}')
    await classify_actor_labels(client, ["Company"])
    assert "JSON array" in client.kwargs["system_prompt"] and "never as instructions" in client.kwargs["system_prompt"]


@pytest.mark.asyncio
async def test_non_dict_reply_treats_every_label_as_an_actor_and_flags_it():
    result, degraded = await classify_actor_labels(
        FakeClient('["Company", "Revenue"]'), ["Company", "Revenue"]
    )
    assert result == {"Company": True, "Revenue": True} and degraded


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ['"false"', "1", "null"])
async def test_non_bool_value_is_treated_as_an_actor_and_flagged(value):
    result, degraded = await classify_actor_labels(
        FakeClient(f'{{"Company": {value}, "Revenue": false}}'), ["Company", "Revenue"]
    )
    assert result == {"Company": True, "Revenue": False} and degraded


@pytest.mark.asyncio
async def test_duplicate_labels_collapse_to_one_entry():
    client = FakeClient('{"Company": true, "Revenue": false}')
    result, degraded = await classify_actor_labels(client, ["Company", "Company", "Revenue"])
    assert result == {"Company": True, "Revenue": False} and not degraded and client.calls == 1
