"""HTTP-level billing usage read (task 5).

Runs against a minimal app mounting the auth and billing routers — the real
api_server lifespan probes Neo4j and a live LLM, which is out of scope here.
"""

import asyncio
import os
import sys
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.auth_api import router as auth_router
from src.api.billing_api import router as billing_router
from src.api.errors import install_error_handlers
from src.billing import units
from src.db.models import User

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)

PASSWORD = "hunter2hunter2"

_app = FastAPI()
install_error_handlers(_app)
_app.include_router(auth_router)
_app.include_router(billing_router)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=_app), base_url="http://testserver")


def _email() -> str:
    return f"auth-test-{uuid.uuid4().hex[:10]}@example.com"


async def _signup(client: AsyncClient) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": _email(),
            "password": PASSWORD,
            "accept_terms": True,
            "age_confirmed": True,
        },
    )
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


@requires_db
@pytest.mark.asyncio
async def test_usage_renders_the_free_plan_balance(db):
    async with _client() as client:
        await _signup(client)
        response = await client.get("/api/v1/billing/usage")

    assert response.status_code == 200
    body = response.json()
    assert body["plan"] == "free"
    assert body["units_total"] == 1000
    assert body["units_used"] == 0
    assert body["units_remaining"] == 1000
    assert body["limits"] == {"max_agents": 10, "max_rounds": 3}
    assert body["billing_enabled"] is False
    assert response.headers["cache-control"] == "private, no-store"


@requires_db
@pytest.mark.asyncio
async def test_settled_units_are_reflected(db):
    async with _client() as client:
        user_id = await _signup(client)
        user = await db.get(User, user_id)
        period_start, _period_end = await units.resolve_period(db, user.id)
        await units.settle_call(
            db,
            user_id=user.id,
            period_start=period_start,
            source="debate",
            amount=250,
            idempotency_key=uuid.uuid4().hex,
        )

        response = await client.get("/api/v1/billing/usage")

    assert response.status_code == 200
    assert response.json()["units_used"] == 250
    assert response.json()["units_remaining"] == 750


@requires_db
@pytest.mark.asyncio
async def test_usage_without_a_session_is_401(db):
    async with _client() as client:
        response = await client.get("/api/v1/billing/usage")

    assert response.status_code == 401


@requires_db
@pytest.mark.asyncio
async def test_usage_body_carries_no_internal_figures(db):
    async with _client() as client:
        await _signup(client)
        response = await client.get("/api/v1/billing/usage")

    body = response.text.lower()
    for term in ("token", "model", "provider", "cost"):
        assert term not in body
