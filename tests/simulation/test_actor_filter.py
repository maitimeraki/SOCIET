import pytest

from src.billing.metering import MeteringError
from src.simulation.actor_filter import classify_actor_labels


class FakeClient:
    def __init__(self, reply: str = "", raises: Exception | None = None):
        self.reply = reply
        self.raises = raises
        self.calls = 0

    async def generate(self, **kwargs) -> str:
        self.calls += 1
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
