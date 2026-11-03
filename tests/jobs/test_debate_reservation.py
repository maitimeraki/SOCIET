"""The worker's side of the reservation: refuse without one, release after success."""

import asyncio
import datetime
import os
import sys
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete

from src.api import run_doc
from src.billing import units
from src.db.engine import get_session_factory
from src.db.models import Job, UsageEvent, UsagePeriod, User
from src.jobs import tasks

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)
pytestmark = [requires_db, pytest.mark.asyncio]

ESTIMATE = 60
_CONFIG = {"max_agents": 2, "max_rounds": 1}
_PAYLOAD = {"query": "Should we tax carbon?", "config": _CONFIG}


@pytest_asyncio.fixture
async def owner(db):
    factory = get_session_factory()
    async with factory() as session:
        user = User(
            email=f"auth-test-reserve-{uuid.uuid4().hex[:10]}@example.com",
            password_hash="not-a-real-hash",
        )
        session.add(user)
        await session.commit()
        user_id = user.id
    try:
        yield SimpleNamespace(id=user_id)
    finally:
        async with factory() as session:
            await session.execute(
                delete(UsageEvent).where(UsageEvent.user_id == user_id)
            )
            await session.execute(delete(Job).where(Job.user_id == user_id))
            await session.execute(
                delete(UsagePeriod).where(UsagePeriod.user_id == user_id)
            )


async def _write_job(owner, *, reserve: bool) -> tuple[str, datetime.datetime | None]:
    """A queued debate row, optionally with a real reservation behind it."""
    job_id = str(uuid.uuid4())
    reserved_units = 0
    period_start = None
    if reserve:
        async with get_session_factory()() as session:
            reservation = await units.reserve_units(
                session,
                user_id=owner.id,
                plan_key="free",
                estimate=ESTIMATE,
            )
            period_start = reservation.period_start
            reserved_units = reservation.amount
    await run_doc.write_run_doc(
        {
            "run_id": job_id,
            "user_id": str(owner.id),
            "status": "queued",
            "query": _PAYLOAD["query"],
            "config": _CONFIG,
            "reserved_units": reserved_units,
            "reserved_period_start": (
                period_start.isoformat() if period_start is not None else None
            ),
            "reserved_at": (
                datetime.datetime.now(datetime.UTC).isoformat()
                if period_start is not None
                else None
            ),
            "result": None,
            "error": None,
        }
    )
    return job_id, period_start


async def _job_and_balance(
    job_id: str, owner, period_start: datetime.datetime | None
) -> tuple[Job, tuple[int, int]]:
    factory = get_session_factory()
    async with factory() as session:
        job = await session.get(Job, uuid.UUID(job_id))
    async with factory() as session:
        start = period_start or (await units.resolve_period(session, owner.id))[0]
        balance = await units.get_balance(session, owner.id, start)
    return job, balance


async def test_debate_core_refuses_without_a_reservation(owner):
    job_id, _ = await _write_job(owner, reserve=False)

    runner = AsyncMock()
    with patch("src.api.debate_api._run_debate_async", new=runner):
        with pytest.raises(RuntimeError, match="reservation missing"):
            await tasks._debate_core(job_id, _PAYLOAD)

    runner.assert_not_awaited()


async def test_debate_core_proceeds_with_a_valid_reservation(owner):
    job_id, _ = await _write_job(owner, reserve=True)

    runner = AsyncMock()
    with patch("src.api.debate_api._run_debate_async", new=runner):
        await tasks._debate_core(job_id, _PAYLOAD)

    runner.assert_awaited_once()


async def test_success_releases_the_leftover_reservation(owner, monkeypatch):
    job_id, period_start = await _write_job(owner, reserve=True)

    async def core(_job_id, _payload):
        return None

    monkeypatch.setitem(tasks.CORES, "debate", core)

    await tasks.execute("debate", job_id, {"user_id": str(owner.id), **_PAYLOAD})

    job, balance = await _job_and_balance(job_id, owner, period_start)
    assert job.status == "complete"
    assert job.reserved_units == 0
    assert balance == (0, 0)


async def _settle(owner, period_start: datetime.datetime, job_id: str, amount: int):
    async with get_session_factory()() as session:
        await units.settle_call(
            session,
            user_id=owner.id,
            period_start=period_start,
            source="debate",
            amount=amount,
            idempotency_key=uuid.uuid4().hex,
            job_id=uuid.UUID(job_id),
        )


async def test_a_partially_settled_failed_run_still_passes_on_retry(owner):
    """The remaining hold is what a retry re-checks, not the original estimate."""
    job_id, period_start = await _write_job(owner, reserve=True)
    await _settle(owner, period_start, job_id, 10)

    job, balance = await _job_and_balance(job_id, owner, period_start)
    assert job.reserved_units == ESTIMATE - 10
    assert balance == (10, ESTIMATE - 10)

    await tasks._assert_reservation(job_id)  # must not raise

    runner = AsyncMock()
    with patch("src.api.debate_api._run_debate_async", new=runner):
        await tasks._debate_core(job_id, _PAYLOAD)
    runner.assert_awaited_once()


async def test_a_sibling_settling_and_releasing_does_not_break_the_other(
    owner, monkeypatch
):
    a_id, a_period = await _write_job(owner, reserve=True)
    b_id, b_period = await _write_job(owner, reserve=True)
    await _settle(owner, a_period, a_id, 10)

    async def core(_job_id, _payload):
        return None

    monkeypatch.setitem(tasks.CORES, "debate", core)
    await tasks.execute("debate", a_id, {"user_id": str(owner.id), **_PAYLOAD})

    await tasks._assert_reservation(b_id)  # A's release took only A's remaining 50
    job_b, balance = await _job_and_balance(b_id, owner, b_period)
    assert job_b.reserved_units == ESTIMATE
    assert balance == (10, ESTIMATE)


async def test_failure_leaves_the_reservation_for_the_lease_sweep(owner, monkeypatch):
    job_id, period_start = await _write_job(owner, reserve=True)

    async def core(_job_id, _payload):
        raise RuntimeError("provider down")

    monkeypatch.setitem(tasks.CORES, "debate", core)

    with pytest.raises(RuntimeError, match="provider down"):
        await tasks.execute("debate", job_id, {"user_id": str(owner.id), **_PAYLOAD})

    job, balance = await _job_and_balance(job_id, owner, period_start)
    assert job.status == "failed"
    assert job.reserved_units == ESTIMATE
    assert balance == (0, ESTIMATE)
