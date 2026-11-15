"""The debate gate: plan caps, atomic reservation, and release on enqueue failure."""

import asyncio
import dataclasses
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
from src.billing.plans import get_plan, get_plans
from src.billing.units import _calendar_month_bounds
from src.db.engine import get_session_factory
from src.db.models import AuditLog, Job, UsageEvent, UsagePeriod, User

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


async def _plan_clamp_audits(user_id: uuid.UUID) -> list[dict]:
    async with get_session_factory()() as session:
        rows = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.user_id == user_id, AuditLog.action == "plan_clamp"
                )
            )
        ).scalars()
        return [row.meta for row in rows]


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
async def client(account, monkeypatch, owned_corpus):
    """The real router in a minimal app; dispatch is a no-op, rows are real."""
    monkeypatch.setattr("src.jobs.queue._dispatch", lambda *args, **kwargs: None)
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(debate_router)
    app.dependency_overrides[current_user] = lambda: account
    transport = ASGITransport(app=app, client=("10.99.8.4", 5000))
    created: list[str] = []
    corpus = await owned_corpus(account.id)
    try:
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as http:
            http.created_jobs = created
            http.graph_id = str(corpus)
            yield http
    finally:
        for job_id in created:
            _DEBATE_JOBS.pop(job_id, None)


async def _post(client, config: dict | None = None):
    body = {"query": "Should we expand into Europe?", "graph_id": client.graph_id}
    if config is not None:
        body["config"] = config
    response = await client.post("/simulate/debate", json=body)
    if response.status_code == 202:
        client.created_jobs.append(response.json()["job_id"])
    return response


async def test_explicit_over_cap_is_rejected_without_a_job_or_reservation(
    client, account
):
    response = await _post(client, {"max_agents": 11})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "plan_limit_exceeded"
    assert await _job_count(account.id) == 0
    assert await _balance(account.id) == (0, 0)


async def test_seat_count_above_twelve_is_rejected_by_the_request_schema(
    client, account
):
    response = await _post(client, {"max_agents": 13})

    assert response.status_code == 422
    assert await _job_count(account.id) == 0


async def test_omitted_config_uses_the_eight_seat_default_and_reserves_the_plan(
    client, account
):
    response = await _post(client)

    assert response.status_code == 202
    job_id = response.json()["job_id"]

    doc = await run_doc.read_run_doc(job_id)
    assert doc["config"]["max_agents"] == 8
    assert doc["config"]["max_rounds"] == 3
    assert doc["config"]["max_pairs_per_round"] == 8

    job = await _job_row(job_id)
    # 8 seats (under the free cap of 10), 3 rounds (clamped from 5), 2 turns per pair
    # at 8 pairs per round: calls = 7 base + (8+2)*8 roster + 3*(1 + (2+2)*8) activation
    # + 3*2*8 turns = 234 calls; 234 * 36 units per call = 8424.
    assert job.reserved_units == 8424
    expected_start, _ = _calendar_month_bounds(datetime.datetime.now(datetime.UTC))
    assert job.reserved_period_start == expected_start
    assert await _balance(account.id) == (0, 8424)


async def test_default_seats_are_clamped_to_the_plan_cap_and_reserved(
    client, account, monkeypatch
):
    capped_free = dataclasses.replace(get_plan("free"), max_agents=6)
    monkeypatch.setattr(
        "src.billing.plans.get_plans",
        lambda: {**get_plans(), "free": capped_free},
    )

    response = await _post(client)

    assert response.status_code == 202
    job_id = response.json()["job_id"]
    doc = await run_doc.read_run_doc(job_id)
    assert doc["config"]["max_agents"] == 6
    assert doc["config"]["max_pairs_per_round"] == 6

    job = await _job_row(job_id)
    # 6 seats, 3 rounds, 6 pairs: 7 + (6+2)*8 + 3*(1 + (2+2)*8) + 3*2*6 = 206 calls; 206 * 36 = 7416.
    assert job.reserved_units == 7416
    assert await _balance(account.id) == (0, 7416)

    clamps = await _plan_clamp_audits(account.id)
    assert len(clamps) == 1
    assert clamps[0]["requested"]["max_agents"] == 8
    assert clamps[0]["applied"]["max_agents"] == 6


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
