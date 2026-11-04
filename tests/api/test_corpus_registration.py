"""The corpus gets its ``datasets`` row when the map is built.

``runs.dataset_id`` carries a foreign key to ``datasets``. Nothing used to write
that table, so convening a decision over a freshly built corpus failed on the
run insert (FK violation) — the golden-path walk found it. Building the map now
registers the corpus with its owner and its name.
"""

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

import src.api.api_server as api_server
from src.api.api_server import simulate_router
from src.auth.deps import current_user
from src.db.engine import get_session_factory
from src.db.models import Dataset, User

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)
pytestmark = [requires_db, pytest.mark.asyncio]

BUILD = "/api/v1/simulate/build_graph"


@pytest_asyncio.fixture
async def accounts():
    factory = get_session_factory()
    made = []
    async with factory() as session:
        for _ in range(2):
            user = User(
                email=f"corpus-reg-{uuid.uuid4().hex[:10]}@example.com",
                password_hash="x",
            )
            session.add(user)
            await session.commit()
            made.append(SimpleNamespace(id=user.id))
    yield made
    async with factory() as session:
        for account in made:
            await session.execute(delete(User).where(User.id == account.id))
        await session.commit()


@pytest_asyncio.fixture
async def client(accounts, monkeypatch):
    owner, _ = accounts
    monkeypatch.setattr(
        api_server, "enqueue_or_http", AsyncMock(return_value="job-corpus-reg")
    )
    # Corpus registration is this file's subject; the reservation itself is
    # covered by tests/api/test_graph_reservation.py. A zero hold keeps two
    # builds in one test from exhausting the free plan between them.
    async def _no_reservation(_db, _user):
        return SimpleNamespace(
            amount=0, period_start=datetime.datetime.now(datetime.UTC)
        )

    monkeypatch.setattr(api_server, "_reserve_graph_job", _no_reservation)
    app = FastAPI()
    app.include_router(simulate_router, prefix="/api/v1")
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=owner.id)
    transport = ASGITransport(app=app, client=("10.99.9.1", 5000))
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


async def _row(dataset_id: uuid.UUID):
    async with get_session_factory()() as session:
        return await session.get(Dataset, dataset_id)


async def test_building_the_map_registers_the_corpus(client, accounts):
    owner, _ = accounts
    corpus_id = uuid.uuid4()

    response = await client.post(
        f"{BUILD}?dataset_id={corpus_id}&corpus_name=Mill%20Street", json=[]
    )

    assert response.status_code == 202, response.text
    row = await _row(corpus_id)
    assert row is not None
    assert row.user_id == owner.id
    assert row.name == "Mill Street"
    # The corpus id is the graph id in this system; account deletion purges by it.
    assert row.graph_id == str(corpus_id)


async def test_a_rebuild_renames_the_same_row(client):
    corpus_id = uuid.uuid4()

    await client.post(f"{BUILD}?dataset_id={corpus_id}&corpus_name=First", json=[])
    await client.post(f"{BUILD}?dataset_id={corpus_id}&corpus_name=Second", json=[])

    async with get_session_factory()() as session:
        count = await session.scalar(
            select(func.count()).select_from(Dataset).where(Dataset.id == corpus_id)
        )
    assert count == 1
    assert (await _row(corpus_id)).name == "Second"


async def test_a_corpus_owned_by_someone_else_is_the_uniform_404(client, accounts):
    _, other = accounts
    corpus_id = uuid.uuid4()
    async with get_session_factory()() as session:
        session.add(
            Dataset(id=corpus_id, user_id=other.id, name="Theirs", graph_id=None)
        )
        await session.commit()

    response = await client.post(
        f"{BUILD}?dataset_id={corpus_id}&corpus_name=Mine", json=[]
    )

    assert response.status_code == 404
    row = await _row(corpus_id)
    assert row.user_id == other.id
    assert row.name == "Theirs"


async def test_a_legacy_non_uuid_id_is_left_unregistered(client):
    response = await client.post(f"{BUILD}?dataset_id=simulation_runtime", json=[])

    assert response.status_code == 202, response.text
    async with get_session_factory()() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(Dataset)
            .where(Dataset.name == "Untitled corpus")
        )
    assert count == 0
