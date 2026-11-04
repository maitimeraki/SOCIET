"""Task 15: the end-to-end billing flow over the real HTTP surface.

Signup → usage → upload → settle → debate → settle → exhaust → 402/403, with
the job enqueue and the extraction patched so no worker, no S3 and no LLM runs.
The routers are the real ones; the rows are real Postgres. This is the one test
that sees the whole pool the plan promises: ingest and debate spend from it.
"""

import asyncio
import datetime
import os
import sys
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from src.api import run_doc
from src.api.auth_api import router as auth_router
from src.api.billing_api import router as billing_router
from src.api.debate_api import _DEBATE_JOBS
from src.api.debate_api import router as debate_router
from src.api.errors import install_error_handlers
from src.api.ingest_api import router as ingest_router
from src.billing import units
from src.billing.plans import get_plan
from src.db.engine import get_session_factory
from src.db.models import AuditLog, Job, Upload, UsageEvent

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)

PASSWORD = "hunter2hunter2"
TEXT = b"Steel tariffs reshape the European market and entry costs."

_app = FastAPI()
install_error_handlers(_app)
_app.include_router(auth_router)
_app.include_router(billing_router)
_app.include_router(ingest_router, prefix="/api/v1")
_app.include_router(debate_router, prefix="/api/v1")


def _client() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=_app, client=("10.99.7.7", 5000)),
        base_url="http://testserver",
    )


def _csrf(client: AsyncClient) -> dict:
    return {"X-CSRF-Token": client.cookies.get("csrf")}


@pytest.fixture(autouse=True)
def _no_worker(monkeypatch):
    """Enqueue writes its rows but never dispatches; nothing runs a worker."""
    monkeypatch.setattr("src.jobs.queue._dispatch", lambda *args, **kwargs: None)


@pytest.fixture(autouse=True)
def _fake_storage(monkeypatch):
    """The upload's object bucket round-trip is the only storage touch."""
    monkeypatch.setattr(
        "src.api.ingest_api.put_upload",
        lambda user_id, upload_id, data: f"{user_id}/{upload_id}",
    )


@pytest.fixture
def bodies():
    """Every response body this flow has seen, for the wire-hygiene check."""
    seen: list[str] = []
    yield seen


async def _signup(client: AsyncClient, bodies: list[str]) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": f"auth-test-flow-{uuid.uuid4().hex[:10]}@example.com",
            "password": PASSWORD,
            "accept_terms": True,
            "age_confirmed": True,
        },
    )
    bodies.append(response.text)
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


async def _usage(client: AsyncClient, bodies: list[str]) -> dict:
    response = await client.get("/api/v1/billing/usage")
    bodies.append(response.text)
    assert response.status_code == 200, response.text
    body = response.json()
    body["period_end_date"] = response.json()["period_end"][:10]
    return body


async def _job_row(factory, job_id: str) -> Job | None:
    async with factory() as session:
        return await session.get(Job, uuid.UUID(job_id))


async def _settle(
    factory,
    *,
    user_id: uuid.UUID,
    period_start: datetime.datetime,
    source: str,
    amount: int,
    key: str,
    job_id: str | None = None,
) -> None:
    async with factory() as session:
        await units.settle_call(
            session,
            user_id=user_id,
            period_start=period_start,
            source=source,
            amount=amount,
            idempotency_key=key,
            job_id=uuid.UUID(job_id) if job_id else None,
        )


async def _release_job(factory, job_id: str) -> int:
    async with factory() as session:
        return await units.release_job_reservation(session, uuid.UUID(job_id))


@requires_db
@pytest.mark.asyncio
async def test_the_billing_flow_shares_one_pool_and_keeps_internals_off_the_wire(
    db, bodies
):
    factory = get_session_factory()
    period_start = None
    user_id = None
    created_jobs: list[str] = []
    try:
        async with _client() as client:
            # 1. Signup (consent + age flags) → the free plan.
            user_id = await _signup(client, bodies)
            usage = await _usage(client, bodies)
            assert usage["plan"] == "free"
            assert usage["units_total"] == get_plan("free").units == 1000
            assert usage["units_used"] == 0
            assert usage["units_remaining"] == 1000
            assert usage["limits"] == {"max_agents": 10, "max_rounds": 3}

            async with factory() as session:
                period_start, period_end = await units.resolve_period(session, user_id)
            assert usage["period_end_date"] == period_end.date().isoformat()

            # 2. Upload: the job row holds a conservative unit ceiling; used
            #    stays 0 while the hold drops the visible remaining.
            upload = await client.post(
                "/api/v1/ingest/files",
                files={"files": ("notes.txt", TEXT, "text/plain")},
                headers=_csrf(client),
            )
            bodies.append(upload.text)
            assert upload.status_code == 202, upload.text
            upload_job_id = upload.json()["job_id"]
            created_jobs.append(upload_job_id)

            upload_job = await _job_row(factory, upload_job_id)
            estimate = units.units_for_chars(len(TEXT))
            assert upload_job.reserved_units == estimate
            assert upload_job.reserved_period_start == period_start

            after_upload = await _usage(client, bodies)
            assert after_upload["units_used"] == 0
            assert after_upload["units_remaining"] == 1000 - estimate

            # 3. Settle the upload's measured chars (the worker's charge).
            async with factory() as session:
                upload_row = (
                    await session.execute(
                        select(Upload).where(Upload.user_id == user_id)
                    )
                ).scalars().one()
            upload_id = str(upload_row.id)

            await _settle(
                factory,
                user_id=user_id,
                period_start=period_start,
                source="ingest",
                amount=units.units_for_chars(len(TEXT)),
                key=f"ingest:{upload_id}",
                job_id=upload_job_id,
            )
            await _release_job(factory, upload_job_id)
            await run_doc.set_job_status(upload_job_id, "completed")

            after_settle = await _usage(client, bodies)
            assert after_settle["units_used"] == estimate
            assert after_settle["units_remaining"] == 1000 - estimate

            # 4. Debate within the caps: agents × rounds × 2 reserved; the
            #    measured call settles against that hold, then the surplus is
            #    released at job end.
            debate = await client.post(
                "/api/v1/simulate/debate",
                json={"query": "Should we expand into Europe?"},
                headers=_csrf(client),
            )
            bodies.append(debate.text)
            assert debate.status_code == 202, debate.text
            debate_job_id = debate.json()["job_id"]
            created_jobs.append(debate_job_id)

            debate_job = await _job_row(factory, debate_job_id)
            free = get_plan("free")
            assert debate_job.reserved_units == free.max_agents * free.max_rounds * 2
            assert debate_job.reserved_units == 60

            during = await _usage(client, bodies)
            assert during["units_used"] == estimate
            assert during["units_remaining"] == 1000 - estimate - 60

            measured = 5
            await _settle(
                factory,
                user_id=user_id,
                period_start=period_start,
                source="debate",
                amount=measured,
                key=f"debate:{uuid.uuid4()}",
                job_id=debate_job_id,
            )
            released = await _release_job(factory, debate_job_id)
            assert released == 55
            await run_doc.set_job_status(debate_job_id, "complete")

            after_debate = await _usage(client, bodies)
            assert after_debate["units_used"] == estimate + measured
            assert after_debate["units_remaining"] == 1000 - estimate - measured

            # 5. Exhaust the pool: the next debate is 402 and names the reset
            #    date; an explicit over-cap request is 403 before any spend.
            remaining = after_debate["units_remaining"]
            await _settle(
                factory,
                user_id=user_id,
                period_start=period_start,
                source="debate",
                amount=remaining,
                key=f"debate:{uuid.uuid4()}",
            )

            exhausted = await _usage(client, bodies)
            assert exhausted["units_remaining"] == 0

            blocked = await client.post(
                "/api/v1/simulate/debate",
                json={"query": "Should we expand into Europe?"},
                headers=_csrf(client),
            )
            bodies.append(blocked.text)
            assert blocked.status_code == 402, blocked.text
            error = blocked.json()["error"]
            assert error["code"] == "payment_required"
            assert exhausted["period_end_date"] in error["message"]

            over_cap = await client.post(
                "/api/v1/simulate/debate",
                json={"query": "Should we expand into Europe?", "config": {"max_agents": 20}},
                headers=_csrf(client),
            )
            bodies.append(over_cap.text)
            assert over_cap.status_code == 403, over_cap.text
            assert over_cap.json()["error"]["code"] == "plan_limit_exceeded"

            # The two refused requests created no job and reserved nothing.
            async with factory() as session:
                jobs = (
                    (
                        await session.execute(
                            select(Job).where(Job.user_id == user_id)
                        )
                    )
                    .scalars()
                    .all()
                )
            assert len(jobs) == 2  # upload + the admitted debate

        # 6. No body leaks an internal figure.
        forbidden = (
            "token",
            "model",
            "provider",
            "cost",
            "unit_cost_usd",
            "unit_tokens",
            "chars_per_unit",
            "stripe",
        )
        for body in bodies:
            lowered = body.lower()
            for term in forbidden:
                assert term not in lowered, (term, body)
    finally:
        for job_id in created_jobs:
            _DEBATE_JOBS.pop(job_id, None)
        if user_id is not None:
            # These two FKs are SET NULL on user delete, so they would outlive
            # the fixture's purge as orphans; remove them while the owner exists.
            async with factory() as session:
                await session.execute(
                    delete(UsageEvent).where(UsageEvent.user_id == user_id)
                )
                await session.execute(
                    delete(AuditLog).where(AuditLog.user_id == user_id)
                )
                await session.commit()
