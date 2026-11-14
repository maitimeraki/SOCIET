"""tasks.execute stores and broadcasts a fixed failure message; the raw text stays in the log."""
import contextlib
from unittest.mock import AsyncMock

import pytest

from src.billing.metering import MeteringError
from src.jobs import tasks

pytestmark = pytest.mark.asyncio

SECRET = "SECRET-JOB-TEXT-4c1d"
RUN_FAILED = "The run failed. Try again, or contact support with the run id."
METERING_STOPPED = (
    "This run stopped: the usage limit for this period was reached, or usage could not be recorded. "
    "Check your usage, then try again."
)


@pytest.fixture
def statuses(monkeypatch):
    calls = []

    async def set_status(job_id, status, error=None, only_if_active=False):
        calls.append((status, error))

    monkeypatch.setattr(tasks, "_set_status", set_status)
    monkeypatch.setattr(tasks, "is_cancelled", lambda job_id: False)
    monkeypatch.setattr(tasks, "_metering_scope", AsyncMock(return_value=contextlib.nullcontext()))
    return calls


async def _execute_with(monkeypatch, exc):
    async def core(_job_id, _payload):
        raise exc

    monkeypatch.setitem(tasks.CORES, "normalize_graph", core)
    with pytest.raises(type(exc)):
        await tasks.execute("normalize_graph", "job-1", {})


async def test_a_generic_failure_stores_the_fixed_message_and_logs_the_exception(monkeypatch, statuses, caplog):
    await _execute_with(monkeypatch, RuntimeError(SECRET))

    assert statuses[-1] == ("failed", RUN_FAILED)
    assert all(SECRET not in str(error) for _, error in statuses)
    assert SECRET in caplog.text


async def test_a_metering_stop_stores_the_authored_message_not_the_raw_text(monkeypatch, statuses):
    await _execute_with(monkeypatch, MeteringError(f"metering failed: {SECRET}"))

    assert statuses[-1] == ("failed", METERING_STOPPED)
    assert all(SECRET not in str(error) for _, error in statuses)
