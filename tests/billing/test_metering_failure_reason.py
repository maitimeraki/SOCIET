"""A settle failure records a fixed authored reason; the raw exception stays in the log."""
import datetime
import uuid
from types import SimpleNamespace

import pytest

from src.billing import metering
from src.billing.metering import metering_scope, record_response

SECRET = "SECRET-SETTLE-TEXT-3f8a"


@pytest.mark.asyncio
async def test_a_settle_failure_records_the_fixed_reason_not_the_exception_text(monkeypatch):
    def explode():
        raise RuntimeError(SECRET)

    monkeypatch.setattr(metering, "get_session_factory", explode)
    response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        model="m",
        _hidden_params={"response_cost": 0.0},
    )
    with metering_scope(
        user_id=uuid.uuid4(),
        period_start=datetime.datetime.now(datetime.UTC),
        source="debate",
    ) as context:
        await record_response(response, provider="openai")

    assert context.failure_reason == "usage could not be recorded"
    assert SECRET not in context.failure_reason
