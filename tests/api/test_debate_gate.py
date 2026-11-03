"""The debate gate: plan caps, atomic reservation, and release on enqueue failure."""

import asyncio
import datetime
import os
import sys
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

import src.api.debate_api as debate_api
from src.api import run_doc
from src.api.debate_api import _DEBATE_JOBS
from src.api.debate_api import router as debate_router
from src.api.errors import install_error_handlers
from src.auth.deps import current_user
from src.billing import units
from src.billing.plans import get_plan
from src.billing.units import _calendar_month_bounds
from src.db.engine import get_session_factory
from src.db.models import Job, UsageEvent, UsagePeriod, User

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)
pytestmark = [requires_db, pytest.mark.asyncio]


async def _job_count(user_id: uuid.UUID) -> int:
    async with get_session_factory()() as session:
        return (
            await session.execute(
                select(func.count()).select_from(Job).where(Job.user_id == user_id)
            )
        ).scalar_one()


async def _job_row(job_id: str) -> Job | None:
    async with get_session_factory()() as session:
        return await session.get(Job, uuid.UUID(job_id))


async def _balance(user_id: uuid.UUID) -> tuple[int, int]:
    async with get_session_factory()() as session:
        period_start, _ = await units.resolve_period(session, user_id)
        return await units.get_balance(session, user_id, period_start)


@pytest_asyncio.fixture
async def account(db):
    """A real free-plan account; the route's caller resolves to its row."""
    factory = get_session_factory()
    async with factory() as session:
        user = User(
            email=f"auth-test-gate-{uuid.uuid4().hex[:10]}@example.com",
            password_hash="not-a-real-hash",
        )
        session.add(user)
        await session.commit()
        user_id = user.id
    try:
        yield SimpleNamespace(id=user_id, plan_key="free")
    finally:
        async with factory() as session:
            await session.execute(
                delete(UsageEvent).where(UsageEvent.user_id == user_id)
            )
            await session.execute(delete(Job).where(Job.user_id == user_id))
            await session.execute(
                delete(UsagePeriod).where(UsagePeriod.user_id == user_id)
            )


@pytest_asyncio.fixture
async def client(account, monkeypatch):
    """The real router in a minimal app; dispatch is a no-op, rows are real."""
    monkeypatch.setattr("src.jobs.queue._dispatch", lambda *args, **kwargs: None)
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(debate_router)
    app.dependency_overrides[current_user] = lambda: account
    transport = ASGITransport(app=app, client=("10.99.8.4", 5000))
    created: list[str] = []
    try:
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as http:
            http.created_jobs = created
            yield http
    finally:
        for job_id in created:
            _DEBATE_JOBS.pop(job_id, None)


async def _post(client, config: dict | None = None):
    body = {"query": "Should we expand into Europe?"}
    if config is not None:
        body["config"] = config
    response = await client.post("/simulate/debate", json=body)
    if response.status_code == 202:
        client.created_jobs.append(response.json()["job_id"])
    return response


async def test_explicit_over_cap_is_rejected_without_a_job_or_reservation(
    client, account
):
    response = await _post(client, {"max_agents": 20})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "plan_limit_exceeded"
    assert await _job_count(account.id) == 0
    assert await _balance(account.id) == (0, 0)


async def test_omitted_config_is_clamped_and_reserved(client, account):
    response = await _post(client)

    assert response.status_code == 202
    job_id = response.json()["job_id"]

    doc = await run_doc.read_run_doc(job_id)
    assert doc["config"]["max_agents"] == 10
    assert doc["config"]["max_rounds"] == 3
    assert doc["config"]["max_pairs_per_round"] == 10

    job = await _job_row(job_id)
    plan = get_plan("free")
    assert job.reserved_units == plan.max_agents * plan.max_rounds * 2 == 60
    expected_start, _ = _calendar_month_bounds(datetime.datetime.now(datetime.UTC))
    assert job.reserved_period_start == expected_start
    assert await _balance(account.id) == (0, 60)


async def test_exhausted_balance_is_402_and_names_the_reset_date(client, account):
    async with get_session_factory()() as session:
        period_start, period_end = await units.resolve_period(session, account.id)
        await units.settle_call(
            session,
            user_id=account.id,
            period_start=period_start,
            source="debate",
            amount=get_plan("free").units,
            idempotency_key=uuid.uuid4().hex,
        )

    response = await _post(client)

    assert response.status_code == 402
    error = response.json()["error"]
    assert error["code"] == "payment_required"
    assert period_end.date().isoformat() in error["message"]
    assert await _job_count(account.id) == 0


async def test_enqueue_failure_releases_the_reservation(client, account, monkeypatch):
    monkeypatch.setattr(
        debate_api, "enqueue_or_http", AsyncMock(side_effect=RuntimeError("redis down"))
    )

    with pytest.raises(RuntimeError, match="redis down"):
        await _post(client)

    assert await _balance(account.id) == (0, 0)


async def test_explicit_rounds_over_cap_is_rejected_but_cap_exactly_is_allowed(
    client, account
):
    denied = await _post(client, {"max_rounds": 10})

    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "plan_limit_exceeded"

    allowed = await _post(client, {"max_agents": 10})

    assert allowed.status_code == 202
    doc = await run_doc.read_run_doc(allowed.json()["job_id"])
    assert doc["config"]["max_agents"] == 10
    assert doc["config"]["max_rounds"] == 3


async def test_dispatch_failure_clears_the_row_and_releases_exactly_once(
    client, account, monkeypatch
):
    def boom(*args, **kwargs):
        raise RuntimeError("redis down")

    monkeypatch.setattr("src.jobs.queue._dispatch", boom)

    with pytest.raises(RuntimeError, match="redis down"):
        await _post(client)

    async with get_session_factory()() as session:
        jobs = (
            (await session.execute(select(Job).where(Job.user_id == account.id)))
            .scalars()
            .all()
        )
    assert len(jobs) == 1
    assert jobs[0].status == "failed"
    assert jobs[0].reserved_units == 0
    assert await _balance(account.id) == (0, 0)

    async with get_session_factory()() as session:
        released = await units.release_expired_reservations(
            session,
            now=datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=2),
        )
    assert released == []
    assert await _balance(account.id) == (0, 0)
