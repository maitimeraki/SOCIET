"""Graph jobs are gated at enqueue: the row carries the unit hold the worker re-checks."""

import asyncio
import os
import sys
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from src.api import api_server
from src.api.errors import install_error_handlers
from src.auth.cookies import verify_csrf
from src.auth.deps import current_user
from src.billing.plans import get_plan
from src.config.settings import get_settings
from src.db.engine import get_db, get_session_factory
from src.db.models import Job, UsageEvent, User
from src.jobs import queue as jobs_queue

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)
pytestmark = [requires_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def owner(db):
    factory = get_session_factory()
    async with factory() as session:
        user = User(
            email=f"graph-reserve-{uuid.uuid4().hex[:10]}@example.com",
            password_hash="x",
        )
        session.add(user)
        await session.commit()
        owner_id = user.id
    yield owner_id
    async with factory() as session:
        await session.execute(delete(UsageEvent).where(UsageEvent.user_id == owner_id))
        await session.execute(delete(User).where(User.id == owner_id))
        await session.commit()


@pytest_asyncio.fixture
async def client(owner, monkeypatch):
    # Dispatch is out of scope: the row is what the worker re-checks.
    monkeypatch.setattr(jobs_queue, "_dispatch", lambda *a, **k: None)
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(api_server.simulate_router)
    app.dependency_overrides[verify_csrf] = lambda: None
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(
        id=owner, plan_key="free"
    )

    factory = get_session_factory()

    async def _db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    transport = ASGITransport(app=app, client=("10.44.0.1", 5000))
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


async def test_ontology_enqueue_is_402_when_the_pool_is_spent(owner, client):
    from src.billing import units

    factory = get_session_factory()
    async with factory() as session:
        period_start, period_end = await units.resolve_period(session, owner)
        await units.settle_call(
            session,
            user_id=owner,
            period_start=period_start,
            source="ontology",
            amount=get_plan("free").units,
            idempotency_key=uuid.uuid4().hex,
        )

    response = await client.post("/simulate/ontology?dataset_id=ds-1", json=[])

    assert response.status_code == 402, response.text
    error = response.json()["error"]
    assert error["code"] == "payment_required"
    assert period_end.date().isoformat() in error["message"]


async def test_ontology_enqueue_holds_min_graph_reserve_and_plan(owner, client):
    response = await client.post(
        "/simulate/ontology?dataset_id=ds-1", json=[]
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]

    factory = get_session_factory()
    async with factory() as session:
        job = await session.get(Job, uuid.UUID(job_id))
    expected = min(get_settings().graph_job_reserve_units, get_plan("free").units)
    assert job.kind == "ontology"
    assert job.reserved_units == expected
    assert job.reserved_period_start is not None
    assert job.reserved_at is not None
