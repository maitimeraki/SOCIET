"""A run's corpus name — set on the request, returned on every summary."""

import asyncio
import os
import sys
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

import src.api.debate_api as debate_api
import src.api.run_doc as run_doc
from src.api.debate_api import router as debate_router
from src.auth.cookies import verify_csrf
from src.auth.deps import current_user
from src.db.engine import get_session_factory
from src.db.models import Run, User

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)
pytestmark = [requires_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def account():
    factory = get_session_factory()
    async with factory() as session:
        user = User(email=f"corpus-label-{uuid.uuid4().hex[:10]}@example.com", password_hash="x")
        session.add(user)
        await session.commit()
        made = SimpleNamespace(id=str(user.id))
    yield made
    async with factory() as session:
        await session.execute(delete(User).where(User.id == uuid.UUID(made.id)))
        await session.commit()


@pytest_asyncio.fixture
async def client(account):
    app = FastAPI()
    app.include_router(debate_router, prefix="/api/v1")
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=uuid.UUID(account.id))
    app.dependency_overrides[verify_csrf] = lambda: None
    # enqueue_or_http is overridden so the test writes the run row directly instead
    # of dispatching a worker task — follow test_debate_api.py's existing override.
    from src.api.jobs_api import enqueue_or_http
    app.dependency_overrides[enqueue_or_http] = AsyncMock(return_value=str(uuid.uuid4()))
    transport = ASGITransport(app=app, client=("10.99.8.1", 5000))
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


async def _label_of(run_id: str) -> str | None:
    factory = get_session_factory()
    async with factory() as session:
        row = (await session.execute(select(Run).where(Run.id == uuid.UUID(run_id)))).scalar_one_or_none()
        return row.corpus_label if row else None


async def test_labelled_run_persists_the_label(account, client, monkeypatch):
    # write_run_doc must accept corpus_label in the doc dict — this is Step 4's change;
    # this test fails until the projection and the write both carry it.
    run_id = str(uuid.uuid4())
    await run_doc.write_run_doc({
        "run_id": run_id, "user_id": account.id, "corpus_label": "European Expansion Analysis",
        "query": "Should we expand?", "status": "queued",
        "events": [], "result": None, "error": None,
    })
    assert await _label_of(run_id) == "European Expansion Analysis"


async def test_unlabelled_run_persists_null(account, client):
    run_id = str(uuid.uuid4())
    await run_doc.write_run_doc({
        "run_id": run_id, "user_id": account.id,
        "query": "Should we expand?", "status": "queued",
        "events": [], "result": None, "error": None,
    })
    assert await _label_of(run_id) is None


async def test_summary_returns_the_label(account, client, monkeypatch):
    run_id = str(uuid.uuid4())
    await run_doc.write_run_doc({
        "run_id": run_id, "user_id": account.id, "corpus_label": "Expansion pack",
        "query": "q", "status": "complete", "events": [], "result": None, "error": None,
    })
    listed = await run_doc.list_run_summaries(uuid.UUID(account.id))
    row = next(item for item in listed["items"] if item["run_id"] == run_id)
    assert row["corpus_label"] == "Expansion pack"
