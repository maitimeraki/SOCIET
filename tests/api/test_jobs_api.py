"""The job surface: the per-user cap and cancellation (plan §5)."""

import asyncio
import os
import sys
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api import run_doc
from src.api.debate_api import router as debate_router
from src.api.errors import install_error_handlers
from src.api.jobs_api import router as jobs_router
from src.api.limits import install_rate_limiter
from src.auth.deps import current_user
from src.db.engine import get_session_factory
from src.db.models import User
from src.jobs import queue as jobs_queue

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)

pytestmark = [requires_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def accounts(db):
    """(owner, other) as ids — jobs.user_id is an FK, so both must be real."""
    factory = get_session_factory()
    made = []
    async with factory() as session:
        for _ in range(2):
            user = User(
                email=f"auth-test-jobs-api-{uuid.uuid4().hex[:10]}@example.com",
                password_hash="not-a-real-hash",
            )
            session.add(user)
            await session.commit()
            made.append(str(user.id))
    return made


def _client(user_id: str, *, debate: bool = False) -> AsyncClient:
    app = FastAPI()
    install_error_handlers(app)
    install_rate_limiter(app)
    app.include_router(jobs_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/simulate")
    if debate:
        app.include_router(debate_router, prefix="/api/v1")
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(
        id=uuid.UUID(str(user_id)), plan_key="free"
    )
    return AsyncClient(
        transport=ASGITransport(app=app, client=("10.99.8.4", 5000)),
        base_url="http://testserver",
    )


async def _run_row(owner: str, status: str = "queued") -> str:
    job_id = str(uuid.uuid4())
    await run_doc.write_run_doc(
        {
            "run_id": job_id,
            "user_id": owner,
            "status": status,
            "query": "Should we tax carbon?",
            "dataset_id": "ds1",
            "config": {},
            "result": None,
            "error": None,
        }
    )
    return job_id


async def _graph_row(owner: str, status: str = "queued") -> str:
    job_id = str(uuid.uuid4())
    await run_doc.write_job_doc(
        {
            "job_id": job_id,
            "user_id": owner,
            "mode": "build_graph",
            "status": status,
            "progress": 0.0,
            "stage": status,
            "error": None,
            "result": None,
        }
    )
    return job_id


def _error(response) -> dict:
    return response.json()["error"]


async def test_the_per_user_cap_answers_429_with_a_retry_after(accounts, monkeypatch):
    owner, _ = accounts
    monkeypatch.setenv("MAX_JOBS_PER_USER", "3")
    from src.config.settings import get_settings

    get_settings.cache_clear()
    try:
        for _ in range(3):
            await _graph_row(owner)

        async with _client(owner, debate=True) as client:
            response = await client.post(
                "/api/v1/simulate/debate", json={"query": "Should we tax carbon?"}
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 429, response.text
    assert _error(response)["code"] == "job_limit_exceeded"
    assert response.headers["Retry-After"] == str(jobs_queue.RETRY_AFTER_SECONDS)


async def _never(*_args, **_kwargs) -> None:
    return None


async def test_a_terminal_job_does_not_count_against_the_cap(accounts, monkeypatch):
    owner, _ = accounts
    monkeypatch.setenv("MAX_JOBS_PER_USER", "1")
    from src.api import debate_api
    from src.config.settings import get_settings

    get_settings.cache_clear()
    # The enqueue is what is under test; the dispatched body (Neo4j, LLM) is not.
    monkeypatch.setattr(debate_api, "_run_debate_async", _never)
    try:
        await _graph_row(owner, status="completed")
        async with _client(owner, debate=True) as client:
            response = await client.post(
                "/api/v1/simulate/debate", json={"query": "Should we tax carbon?"}
            )
    finally:
        get_settings.cache_clear()
        await jobs_queue.drain_inline()

    assert response.status_code == 202, response.text


async def test_cancelling_a_queued_job_cancels_it_immediately(accounts):
    owner, _ = accounts
    job_id = await _graph_row(owner)

    async with _client(owner) as client:
        response = await client.delete(f"/api/v1/jobs/{job_id}")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
    assert (await run_doc.read_job_doc(job_id))["status"] == "cancelled"


async def test_cancelling_a_running_job_sets_the_flag(accounts):
    owner, _ = accounts
    job_id = await _run_row(owner, status="running")
    try:
        async with _client(owner) as client:
            response = await client.delete(f"/api/v1/jobs/{job_id}")

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "cancelling"
        assert jobs_queue.is_cancelled(job_id) is True
        # Still running until the worker reaches its next boundary.
        assert (await run_doc.read_run_head(job_id))["status"] == "running"
    finally:
        jobs_queue.clear_cancel(job_id)


async def test_cancelling_a_finished_job_is_a_conflict(accounts):
    owner, _ = accounts
    job_id = await _run_row(owner, status="complete")

    async with _client(owner) as client:
        response = await client.delete(f"/api/v1/jobs/{job_id}")

    assert response.status_code == 409, response.text
    assert _error(response)["code"] == "job_not_cancellable"


async def test_cancelling_a_foreign_job_is_not_found(accounts):
    owner, other = accounts
    job_id = await _graph_row(owner)

    async with _client(other) as client:
        response = await client.delete(f"/api/v1/jobs/{job_id}")

    assert response.status_code == 404, response.text
    assert _error(response)["code"] == "not_found"
    assert (await run_doc.read_job_doc(job_id))["status"] == "queued"


async def test_cancelling_an_unknown_job_is_not_found(accounts):
    owner, _ = accounts

    async with _client(owner) as client:
        response = await client.delete(f"/api/v1/jobs/{uuid.uuid4()}")

    assert response.status_code == 404, response.text


async def test_the_legacy_mount_cancels_too(accounts):
    owner, _ = accounts
    job_id = await _graph_row(owner)

    async with _client(owner) as client:
        response = await client.delete(f"/simulate/jobs/{job_id}")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
