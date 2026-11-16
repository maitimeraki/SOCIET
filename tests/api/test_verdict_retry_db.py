"""The verdict retry's in-flight guard, against the real jobs table (migration 0008).

DB-gated: skipped unless DATABASE_URL is set. The pure gate is covered without a database in
test_verdict_retry_gate.py.
"""

import datetime
import os
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import delete

from src.api import run_doc
from src.db.engine import get_session_factory
from src.db.models import Run, User

requires_db = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set")
pytestmark = [requires_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def run():
    async with get_session_factory()() as session:
        user = User(email=f"verdict-retry-{uuid.uuid4().hex[:10]}@example.com", password_hash="not-a-real-hash")
        session.add(user)
        await session.commit()
        user_id = str(user.id)
    run_id = str(uuid.uuid4())
    await run_doc.write_run_doc({
        "run_id": run_id, "user_id": user_id, "created_at": "2026-11-01T00:00:00+00:00",
        "status": "complete", "query": "Should we expand?", "config": {}, "error": None,
        "result": {"status": "not_produced", "retry_inputs": {"context": "", "turns": []}},
    })
    try:
        yield SimpleNamespace(run_id=run_id, user_id=user_id)
    finally:
        async with get_session_factory()() as session:
            await session.execute(delete(Run).where(Run.id == uuid.UUID(run_id)))
            await session.execute(delete(User).where(User.id == uuid.UUID(user_id)))
            await session.commit()


def _insert(run, job_id: str) -> dict:
    now = datetime.datetime.now(datetime.UTC).isoformat()
    return {
        "job_id": job_id, "run_id": run.run_id, "user_id": run.user_id,
        "created_at": now, "reserved_units": 3,
        "reserved_period_start": "2026-11-01T00:00:00+00:00", "reserved_at": now,
    }


async def test_a_second_in_flight_retry_for_the_same_run_is_refused_by_the_database(run):
    await run_doc.write_verdict_job(**_insert(run, str(uuid.uuid4())))

    with pytest.raises(run_doc.VerdictJobInFlight):
        await run_doc.write_verdict_job(**_insert(run, str(uuid.uuid4())))
    assert await run_doc.verdict_job_in_flight(run.run_id)


async def test_a_finished_retry_frees_the_run_for_a_new_one(run):
    first = str(uuid.uuid4())
    await run_doc.write_verdict_job(**_insert(run, first))
    await run_doc.set_job_status(first, "completed")

    assert not await run_doc.verdict_job_in_flight(run.run_id)
    await run_doc.write_verdict_job(**_insert(run, str(uuid.uuid4())))
    assert await run_doc.verdict_job_in_flight(run.run_id)


async def test_the_reaper_fails_a_stuck_queued_retry_and_releases_its_hold(run):
    from src.db.models import Job

    stuck = str(uuid.uuid4())
    await run_doc.write_verdict_job(**{**_insert(run, stuck), "created_at": "2020-01-01T00:00:00+00:00"})

    await run_doc.sweep_interrupted()

    async with get_session_factory()() as session:
        row = await session.get(Job, uuid.UUID(stuck))
    assert row.status == "failed" and row.error == "interrupted"
    assert row.reserved_units == 0
    assert not await run_doc.verdict_job_in_flight(run.run_id)
    await run_doc.write_verdict_job(**_insert(run, str(uuid.uuid4())))
    assert await run_doc.verdict_job_in_flight(run.run_id)


async def test_the_reaper_leaves_a_recent_queued_retry_alone(run):
    from src.db.models import Job

    recent = str(uuid.uuid4())
    await run_doc.write_verdict_job(**_insert(run, recent))

    await run_doc.sweep_interrupted()

    async with get_session_factory()() as session:
        row = await session.get(Job, uuid.UUID(recent))
    assert row.status == "queued" and row.reserved_units == 3
    assert await run_doc.verdict_job_in_flight(run.run_id)
