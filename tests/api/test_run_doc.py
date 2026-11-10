"""runs.dataset_id — the corpus a run is about, on the row where the graph route reads it."""

import asyncio
import os
import sys
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

import src.api.run_doc as run_doc
from src.db.engine import get_session_factory
from src.db.models import Dataset, Run, User

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
        user = User(
            email=f"run-doc-{uuid.uuid4().hex[:10]}@example.com", password_hash="x"
        )
        session.add(user)
        await session.commit()
        made = SimpleNamespace(id=str(user.id))
    yield made
    async with factory() as session:
        await session.execute(delete(User).where(User.id == uuid.UUID(made.id)))
        await session.commit()


async def _add_corpus(user_id: str, dataset_id: str) -> None:
    """``runs.dataset_id`` is an FK to ``datasets.id``: the parent row comes first."""
    factory = get_session_factory()
    async with factory() as session:
        session.add(
            Dataset(
                id=uuid.UUID(dataset_id),
                user_id=uuid.UUID(user_id),
                name="run-doc corpus",
            )
        )
        await session.commit()


async def _row_for(run_id: str) -> Run | None:
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(Run).where(Run.id == uuid.UUID(run_id)))
        return result.scalar_one_or_none()


async def test_dataset_id_persists_on_the_row(account):
    run_id = str(uuid.uuid4())
    dataset_id = str(uuid.uuid4())
    await _add_corpus(account.id, dataset_id)
    await run_doc.write_run_doc({
        "run_id": run_id, "user_id": account.id, "dataset_id": dataset_id,
        "query": "Should we expand?", "status": "queued",
        "events": [], "result": None, "error": None,
    })
    row = await _row_for(run_id)
    assert row is not None
    assert str(row.dataset_id) == dataset_id


async def test_document_without_dataset_id_still_writes(account):
    """An older caller that carries no dataset_id writes fine; the column stays null."""
    run_id = str(uuid.uuid4())
    await run_doc.write_run_doc({
        "run_id": run_id, "user_id": account.id,
        "query": "Should we expand?", "status": "queued",
        "events": [], "result": None, "error": None,
    })
    row = await _row_for(run_id)
    assert row is not None
    assert row.dataset_id is None
