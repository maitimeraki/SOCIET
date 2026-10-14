"""The RQ dispatch path, driven by a real worker against the local Redis.

``rq.SimpleWorker`` runs jobs inline (no fork), so this works on Windows — and
it is the real path: a real enqueue, the real ``src/jobs/tasks.py`` target, the
real lifecycle, and the rows as the only assertion surface.
"""
import asyncio
import os
import uuid

import pytest
from rq import SimpleWorker

from src.api import run_doc
from src.config.settings import get_settings
from src.db.engine import get_engine, get_session_factory
from src.db.models import User
from src.jobs import queue as jobs_queue
from src.jobs import tasks

requires_db = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set")

EMAIL = "auth-test-rq-%@example.com"


async def _noop_core(_job_id, _payload) -> None:
    return None


def _run(coro):
    """One ``asyncio.run``, disposing the engine after — a pooled async
    connection cannot be reused across event loops (tests/conftest.py)."""

    async def _wrapped():
        try:
            return await coro
        finally:
            await get_engine().dispose()

    return asyncio.run(_wrapped())


async def _make_owner() -> str:
    factory = get_session_factory()
    async with factory() as session:
        user = User(
            email=EMAIL.replace("%", uuid.uuid4().hex[:10]), password_hash="not-a-real-hash"
        )
        session.add(user)
        await session.commit()
        return str(user.id)


async def _drop_owner(owner: str) -> None:
    from sqlalchemy import delete

    factory = get_session_factory()
    async with factory() as session:
        await session.execute(delete(User).where(User.id == uuid.UUID(owner)))
        await session.commit()


@requires_db
def test_a_burst_worker_drives_a_job_queued_to_completed(monkeypatch):
    monkeypatch.setenv("QUEUE_MODE", "rq")
    get_settings.cache_clear()
    monkeypatch.setitem(tasks.CORES, "normalize_graph", _noop_core)

    owner = _run(_make_owner())
    try:
        job_id = _run(
            jobs_queue.enqueue("normalize_graph", {"user_id": owner, "dataset_id": "ds1"})
        )
        queued = _run(run_doc.read_job_doc(job_id))
        assert queued["status"] == "queued"
        assert jobs_queue.get_queue().count == 1

        worker = SimpleWorker([jobs_queue.get_queue()], connection=jobs_queue.get_redis())
        worker.work(burst=True)

        done = _run(run_doc.read_job_doc(job_id))
        assert done["status"] == "completed"
        assert jobs_queue.get_queue().count == 0
    finally:
        _run(_drop_owner(owner))
        get_settings.cache_clear()
