"""The run's graph, over REST, owner-checked — the replay path's corpus seed."""

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
from sqlalchemy import delete

import src.api.debate_api as debate_api
import src.api.run_doc as run_doc
from src.api.debate_api import router as debate_router
from src.auth.deps import current_user
from src.db.engine import get_session_factory
from src.db.models import Dataset, User

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)
pytestmark = [requires_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def accounts():
    factory = get_session_factory()
    made = []
    async with factory() as session:
        for _ in range(2):
            user = User(
                email=f"graph-route-{uuid.uuid4().hex[:10]}@example.com",
                password_hash="x",
            )
            session.add(user)
            await session.commit()
            made.append(SimpleNamespace(id=str(user.id)))
    yield made
    async with factory() as session:
        for account in made:
            await session.execute(delete(User).where(User.id == uuid.UUID(account.id)))
        await session.commit()


@pytest_asyncio.fixture
async def client(accounts):
    owner, _ = accounts
    app = FastAPI()
    for router, prefix in [(debate_router, ""), (debate_router, "/api/v1")]:
        app.include_router(router, prefix=prefix)
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(
        id=uuid.UUID(owner.id)
    )
    transport = ASGITransport(app=app, client=("10.99.8.1", 5000))
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


@pytest.fixture
def snapshot(monkeypatch):
    """Stand-in for the Neo4j read — the route test must not need Neo4j."""
    payload = {
        "nodes": [
            {"id": "ent_1", "label": "Expansion", "type": "Concept", "properties": {}}
        ],
        "edges": [
            {
                "key": "ent_1|ent_2|REL",
                "source": "ent_1",
                "target": "ent_2",
                "label": "REL",
                "properties": {},
            }
        ],
        "labels": ["Concept"],
        "chunk_count": 3,
    }
    fake = AsyncMock(return_value=payload)
    monkeypatch.setattr(debate_api, "read_graph_snapshot", fake)
    return fake


@pytest.fixture
def emptied_snapshot(monkeypatch):
    """A corpus emptied while Neo4j is healthy: the read succeeds and returns nothing."""
    fake = AsyncMock(
        return_value={"nodes": [], "edges": [], "labels": [], "chunk_count": 0}
    )
    monkeypatch.setattr(debate_api, "read_graph_snapshot", fake)
    return fake


async def _add_corpus(user_id: str, dataset_id: str) -> None:
    """``runs.dataset_id`` is an FK to ``datasets.id``: the parent row comes first."""
    factory = get_session_factory()
    async with factory() as session:
        session.add(
            Dataset(
                id=uuid.UUID(dataset_id),
                user_id=uuid.UUID(user_id),
                name="graph-route corpus",
            )
        )
        await session.commit()


async def _write_run(user_id: str, dataset_id: str | None) -> str:
    run_id = str(uuid.uuid4())
    doc = {
        "run_id": run_id,
        "user_id": user_id,
        "query": "q",
        "status": "complete",
        "events": [],
        "result": None,
        "error": None,
    }
    if dataset_id is not None:
        doc["dataset_id"] = dataset_id
        await _add_corpus(user_id, dataset_id)
    await run_doc.write_run_doc(doc)
    return run_id


async def test_owned_run_returns_five_fields(accounts, client, snapshot):
    owner, _ = accounts
    run_id = await _write_run(owner.id, str(uuid.uuid4()))
    response = await client.get(f"/api/v1/simulate/debates/{run_id}/graph")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"dataset_id", "nodes", "edges", "labels", "chunk_count"}
    assert body["nodes"] and body["labels"] and body["chunk_count"] == 3


async def test_another_users_run_is_404_not_403(accounts, client, snapshot):
    _, other = accounts
    run_id = await _write_run(other.id, str(uuid.uuid4()))
    response = await client.get(f"/api/v1/simulate/debates/{run_id}/graph")
    assert response.status_code == 404


async def test_unknown_run_is_404(accounts, client, snapshot):
    response = await client.get(f"/api/v1/simulate/debates/{uuid.uuid4()}/graph")
    assert response.status_code == 404


async def test_run_without_corpus_is_typed_404(accounts, client, snapshot):
    owner, _ = accounts
    run_id = await _write_run(owner.id, None)
    response = await client.get(f"/api/v1/simulate/debates/{run_id}/graph")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "no_corpus"


async def test_emptied_corpus_is_typed_404(accounts, client, emptied_snapshot):
    owner, _ = accounts
    run_id = await _write_run(owner.id, str(uuid.uuid4()))
    response = await client.get(f"/api/v1/simulate/debates/{run_id}/graph")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "corpus_gone"


# The unmocked read, end to end: a corpus id Neo4j holds nothing under. Its
# corpus_gone answer comes from the zero-node branch when Neo4j is reachable and
# from the read-failure branch when it is not — the deterministic cover for the
# zero-node branch is `test_emptied_corpus_is_typed_404` above.
async def test_corpus_absent_from_graph_is_typed_404(accounts, client):
    owner, _ = accounts
    run_id = await _write_run(owner.id, str(uuid.uuid4()))
    response = await client.get(f"/api/v1/simulate/debates/{run_id}/graph")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "corpus_gone"
