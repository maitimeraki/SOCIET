"""Audit log: the action matrix is recorded; a failed write never breaks the
business operation (plan §8)."""

import asyncio
import os
import sys
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src import audit
from src.api import run_doc
from src.api.errors import install_error_handlers
from src.api.jobs_api import router as jobs_router
from src.auth.deps import current_user
from src.db.engine import get_db, get_session_factory
from src.db.models import AuditLog, User

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
            email=f"auth-test-audit-{uuid.uuid4().hex[:10]}@example.com",
            password_hash="not-a-real-hash",
        )
        session.add(user)
        await session.commit()
        return str(user.id)


async def test_every_action_writes_a_row(owner, db):
    for action in audit.ACTIONS:
        await audit.record(
            db, action, user_id=owner, target="thing", ip="10.0.0.1", meta={"k": 1}
        )

    rows = (
        (
            await db.execute(
                select(AuditLog.action).where(AuditLog.user_id == uuid.UUID(owner))
            )
        )
        .scalars()
        .all()
    )
    assert set(rows) == set(audit.ACTIONS)
    assert "me" not in audit.ACTIONS  # read-only noise is not audited


class _BrokenSession:
    """A session whose audit write fails — the closed/invalid-session case."""

    def add(self, _obj) -> None:
        pass

    async def commit(self) -> None:
        raise RuntimeError("audit connection lost")

    async def rollback(self) -> None:
        pass


async def _broken_db():
    yield _BrokenSession()


async def _queued_job(owner: str) -> str:
    job_id = str(uuid.uuid4())
    await run_doc.write_job_doc(
        {
            "job_id": job_id,
            "user_id": owner,
            "mode": "build_graph",
            "status": "queued",
            "progress": 0.0,
            "stage": "queued",
            "error": None,
            "result": None,
        }
    )
    return job_id


async def test_a_failed_audit_write_does_not_break_the_request(owner):
    """The route's only use of the injected db is the audit write, so a broken
    audit session proves the business operation (cancel) still completes."""
    job_id = await _queued_job(owner)

    app = FastAPI()
    install_error_handlers(app)
    app.include_router(jobs_router, prefix="/api/v1")
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(
        id=uuid.UUID(owner)
    )
    app.dependency_overrides[get_db] = _broken_db

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("10.1.2.3", 5000)),
        base_url="http://testserver",
    ) as client:
        response = await client.delete(f"/api/v1/jobs/{job_id}")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
    # And the business change really landed, despite the audit failure.
    assert (await run_doc.read_job_doc(job_id))["status"] == "cancelled"
