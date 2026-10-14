"""Queue helpers: cancel flags, dispatch-mode selection, the per-user cap."""
import asyncio
import os
import uuid

import pytest
import pytest_asyncio

from src.api import run_doc
from src.config.settings import get_settings
from src.db.engine import get_session_factory
from src.db.models import User
from src.jobs import queue as jobs_queue

requires_db = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set")


@pytest_asyncio.fixture
async def owner(db):
    factory = get_session_factory()
    async with factory() as session:
        user = User(
            email=f"auth-test-jobs-{uuid.uuid4().hex[:10]}@example.com",
            password_hash="not-a-real-hash",
        )
        session.add(user)
        await session.commit()
        user_id = str(user.id)
    return user_id


def test_timeout_is_per_kind(monkeypatch):
    monkeypatch.setenv("JOB_TIMEOUT_DEBATE_SECONDS", "1234")
    monkeypatch.setenv("JOB_TIMEOUT_GRAPH_SECONDS", "56")
    get_settings.cache_clear()
    try:
        assert jobs_queue.timeout_for("debate") == 1234
        assert jobs_queue.timeout_for("ontology") == 56
        assert jobs_queue.timeout_for("normalize_graph") == 56
    finally:
        get_settings.cache_clear()


def test_cancel_ttl_outlives_every_job_timeout(monkeypatch):
    monkeypatch.setenv("JOB_TIMEOUT_DEBATE_SECONDS", "1000")
    monkeypatch.setenv("JOB_TIMEOUT_GRAPH_SECONDS", "10")
    get_settings.cache_clear()
    try:
        assert jobs_queue.cancel_ttl_seconds() > 1000
    finally:
        get_settings.cache_clear()


def test_cancel_flag_round_trips_through_redis():
    job_id = f"cancel-{uuid.uuid4()}"
    try:
        assert jobs_queue.is_cancelled(job_id) is False
        jobs_queue.set_cancel(job_id)
        assert jobs_queue.is_cancelled(job_id) is True
        assert jobs_queue.cancel_check(job_id)() is True
        jobs_queue.clear_cancel(job_id)
        assert jobs_queue.is_cancelled(job_id) is False
    finally:
        jobs_queue.clear_cancel(job_id)


@pytest.mark.asyncio
async def test_a_kind_this_build_cannot_run_is_a_validation_error():
    with pytest.raises(jobs_queue.JobValidationError):
        await jobs_queue.enqueue("time_travel", {"user_id": str(uuid.uuid4())})


@pytest.mark.asyncio
async def test_a_payload_without_an_owner_is_a_validation_error():
    with pytest.raises(jobs_queue.JobValidationError):
        await jobs_queue.enqueue("debate", {"query": "Should we tax carbon?"})


@requires_db
@pytest.mark.asyncio
async def test_the_cap_counts_every_kind_and_releases_on_a_terminal_state(owner, monkeypatch):
    monkeypatch.setenv("MAX_JOBS_PER_USER", "2")
    get_settings.cache_clear()
    try:
        first = await jobs_queue.enqueue("ontology", {"user_id": owner, "dataset_id": "ds1"})
        await run_doc.write_job_doc(
            {
                "job_id": str(uuid.uuid4()), "user_id": owner, "mode": "build_graph",
                "status": "queued", "progress": 0.0, "stage": "queued",
                "error": None, "result": None,
            }
        )

        with pytest.raises(jobs_queue.JobLimitExceeded) as raised:
            await jobs_queue.enqueue("debate", {"user_id": owner, "query": "q"})

        assert raised.value.limit == 2

        # A terminal row is not in flight, so its slot is free again.
        await run_doc.set_job_status(first, "completed")
        await jobs_queue.enqueue("debate", {"user_id": owner, "query": "q"})
    finally:
        get_settings.cache_clear()
        await jobs_queue.drain_inline()


@requires_db
@pytest.mark.asyncio
async def test_a_dispatch_failure_marks_the_row_failed_not_queued(owner, monkeypatch):
    """Redis down at dispatch must not orphan a `queued` row that burns a cap
    slot forever (nothing sweeps queued rows, and the cap counts them)."""
    seen: dict = {}

    def boom(kind, job_id, payload):
        seen["job_id"] = job_id
        raise RuntimeError("redis down")

    monkeypatch.setattr(jobs_queue, "_dispatch", boom)

    with pytest.raises(RuntimeError, match="redis down"):
        await jobs_queue.enqueue("normalize_graph", {"user_id": owner, "dataset_id": "ds1"})

    doc = await run_doc.read_job_doc(seen["job_id"])
    assert (doc["status"], doc["error"]) == ("failed", "redis down")
    assert await run_doc.count_active_jobs(owner) == 0

