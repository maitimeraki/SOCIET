"""Lifecycle: queued → running → complete|failed|cancelled, written to the rows."""

import asyncio
import os
import uuid

import pytest
import pytest_asyncio

from src.api import run_doc
from src.db.engine import get_session_factory
from src.db.models import User
from src.jobs import queue as jobs_queue
from src.jobs import tasks

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)

pytestmark = [requires_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def owner(db):
    factory = get_session_factory()
    async with factory() as session:
        user = User(
            email=f"auth-test-lifecycle-{uuid.uuid4().hex[:10]}@example.com",
            password_hash="not-a-real-hash",
        )
        session.add(user)
        await session.commit()
        return str(user.id)


async def _queued_job(owner: str) -> str:
    job_id = str(uuid.uuid4())
    await run_doc.write_job_doc(
        {
            "job_id": job_id,
            "user_id": owner,
            "mode": "normalize_graph",
            "status": "queued",
            "progress": 0.0,
            "stage": "queued",
            "error": None,
            "result": None,
        }
    )
    return job_id


async def _status(job_id: str) -> str:
    return (await run_doc.read_job_doc(job_id))["status"]


async def test_a_successful_job_lands_completed(owner, monkeypatch):
    job_id = await _queued_job(owner)
    seen: list[str] = []

    async def core(_job_id, _payload):
        seen.append(await _status(_job_id))
        return None

    monkeypatch.setitem(tasks.CORES, "normalize_graph", core)

    await tasks.execute("normalize_graph", job_id, {"user_id": owner})

    assert seen == ["running"]  # running is written before the body starts
    assert await _status(job_id) == "completed"


async def test_a_raising_job_lands_failed_with_the_error_text(owner, monkeypatch):
    job_id = await _queued_job(owner)

    async def core(_job_id, _payload):
        raise RuntimeError("neo4j unreachable")

    monkeypatch.setitem(tasks.CORES, "normalize_graph", core)

    with pytest.raises(RuntimeError, match="neo4j unreachable"):
        await tasks.execute("normalize_graph", job_id, {"user_id": owner})

    doc = await run_doc.read_job_doc(job_id)
    assert (doc["status"], doc["error"]) == ("failed", "neo4j unreachable")


async def test_a_job_over_its_timeout_lands_failed(owner, monkeypatch):
    job_id = await _queued_job(owner)

    async def core(_job_id, _payload):
        await asyncio.sleep(30)

    monkeypatch.setitem(tasks.CORES, "normalize_graph", core)
    monkeypatch.setattr(tasks, "timeout_for", lambda _kind: 0.05)

    with pytest.raises((asyncio.TimeoutError, TimeoutError)):
        await tasks.execute("normalize_graph", job_id, {"user_id": owner})

    doc = await run_doc.read_job_doc(job_id)
    assert doc["status"] == "failed"
    assert "exceeded its 0.05s timeout" in doc["error"]


async def test_a_job_cancelled_before_it_starts_never_runs(owner, monkeypatch):
    job_id = await _queued_job(owner)
    ran: list[bool] = []

    async def core(_job_id, _payload):
        ran.append(True)

    monkeypatch.setitem(tasks.CORES, "normalize_graph", core)
    jobs_queue.set_cancel(job_id)

    await tasks.execute("normalize_graph", job_id, {"user_id": owner})

    assert ran == []
    assert await _status(job_id) == "cancelled"


async def test_a_cancel_seen_between_boundaries_lands_cancelled(owner, monkeypatch):
    """The body reports cancellation by raising JobCancelled — a terminal
    `cancelled`, and NOT a failure that RQ would retry."""
    job_id = await _queued_job(owner)

    async def core(_job_id, _payload):
        assert jobs_queue.is_cancelled(_job_id) is False
        jobs_queue.set_cancel(_job_id)
        raise tasks.JobCancelled("cancelled at round 2")

    monkeypatch.setitem(tasks.CORES, "normalize_graph", core)

    await tasks.execute("normalize_graph", job_id, {"user_id": owner})

    assert await _status(job_id) == "cancelled"
    jobs_queue.clear_cancel(job_id)


async def test_a_body_that_already_failed_is_not_marked_successful(owner, monkeypatch):
    """The graph bodies write their own terminal state and swallow the raise;
    the lifecycle's success marker must not overwrite it."""
    job_id = await _queued_job(owner)

    async def core(_job_id, _payload):
        await run_doc.set_job_status(_job_id, "failed", error="all chunks failed")

    monkeypatch.setitem(tasks.CORES, "normalize_graph", core)

    await tasks.execute("normalize_graph", job_id, {"user_id": owner})

    doc = await run_doc.read_job_doc(job_id)
    assert (doc["status"], doc["error"]) == ("failed", "all chunks failed")
