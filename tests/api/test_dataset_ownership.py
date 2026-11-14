"""Audit C1 (fixes 5, 6): a graph route takes only a UUID dataset id, and the caller owns it.

A non-uuid id (the old shared ``simulation_runtime`` default) is refused before
any handler runs. A dataset owned by someone else and an unknown dataset get the
same 404 body, so existence is never leaked. The ontology and build routes
register a fresh corpus on first use (the browser calls ontology before the build
creates the row), so for them "unknown" means "register", never "404".
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
from sqlalchemy import delete

import src.api.api_server as api_server
import src.api.debate_api as debate_api
from src.api.api_server import simulate_router
from src.api.debate_api import router as debate_router
from src.api.errors import install_error_handlers
from src.auth.deps import current_user
from src.db.engine import get_db, get_session_factory
from src.db.models import Dataset, User
from src.jobs import queue as jobs_queue

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)

GRAPH_ROUTES = [
    "/simulate/ontology",
    "/simulate/build_graph",
    "/simulate/normalize_graph",
]
QUERY = "Should we tax carbon?"


def _app(user_id: uuid.UUID) -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(simulate_router)
    app.include_router(debate_router)
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(
        id=user_id, plan_key="free"
    )
    return app


@pytest_asyncio.fixture
async def bare_client(monkeypatch):
    """Reaches only the validation layer: no account, no database row needed."""
    monkeypatch.setattr(
        api_server, "enqueue_or_http", AsyncMock(return_value="job-bare")
    )
    app = _app(uuid.uuid4())

    async def _no_session():
        yield None

    app.dependency_overrides[get_db] = _no_session
    transport = ASGITransport(app=app, client=("10.99.9.2", 5000))
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


@pytest_asyncio.fixture
async def accounts():
    factory = get_session_factory()
    made = []
    async with factory() as session:
        for _ in range(2):
            user = User(
                email=f"dataset-own-{uuid.uuid4().hex[:10]}@example.com",
                password_hash="x",
            )
            session.add(user)
            await session.commit()
            made.append(SimpleNamespace(id=user.id))
    yield made
    async with factory() as session:
        for account in made:
            await session.execute(delete(Dataset).where(Dataset.user_id == account.id))
            await session.execute(delete(User).where(User.id == account.id))
        await session.commit()


@pytest_asyncio.fixture
async def client(accounts, monkeypatch):
    owner, _ = accounts
    monkeypatch.setattr(
        api_server, "enqueue_or_http", AsyncMock(return_value="job-owned")
    )

    async def _no_reservation(_db, _user):
        return SimpleNamespace(
            amount=0, period_start=datetime.datetime.now(datetime.UTC)
        )

    monkeypatch.setattr(api_server, "_reserve_graph_job", _no_reservation)
    monkeypatch.setattr(debate_api, "_run_debate_async", AsyncMock())
    monkeypatch.setattr(jobs_queue, "_dispatch", lambda *args, **kwargs: None)
    transport = ASGITransport(app=_app(owner.id), client=("10.99.9.3", 5000))
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


async def _own_corpus(user_id: uuid.UUID) -> uuid.UUID:
    corpus = uuid.uuid4()
    async with get_session_factory()() as session:
        session.add(Dataset(id=corpus, user_id=user_id, name="Mine"))
        await session.commit()
    return corpus


async def _row(dataset_id: uuid.UUID):
    async with get_session_factory()() as session:
        return await session.get(Dataset, dataset_id)


async def _post_graph_route(http, path: str, dataset_id: str):
    if path == "/simulate/normalize_graph":
        return await http.post(f"{path}?dataset_id={dataset_id}")
    return await http.post(f"{path}?dataset_id={dataset_id}", json=[])


# --- a non-uuid dataset id never reaches a handler ---------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("path", GRAPH_ROUTES)
async def test_a_non_uuid_dataset_is_refused_on_graph_routes(bare_client, path):
    response = await _post_graph_route(bare_client, path, "simulation_runtime")

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_a_debate_without_a_graph_id_is_refused(bare_client):
    response = await bare_client.post("/simulate/debate", json={"query": QUERY})

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_a_debate_with_the_shared_default_graph_id_is_refused(bare_client):
    response = await bare_client.post(
        "/simulate/debate",
        json={"query": QUERY, "graph_id": "simulation_runtime"},
    )

    assert response.status_code == 422, response.text


# --- a dataset the caller does not own is the uniform 404 --------------------


@requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize("path", GRAPH_ROUTES)
async def test_a_foreign_dataset_is_the_uniform_404(client, accounts, path):
    _, other = accounts
    theirs = await _own_corpus(other.id)

    response = await _post_graph_route(client, path, str(theirs))

    assert response.status_code == 404, response.text


@requires_db
@pytest.mark.asyncio
async def test_a_foreign_debate_graph_id_is_the_uniform_404(client, accounts):
    _, other = accounts
    theirs = await _own_corpus(other.id)

    response = await client.post(
        "/simulate/debate", json={"query": QUERY, "graph_id": str(theirs)}
    )

    assert response.status_code == 404, response.text


@requires_db
@pytest.mark.asyncio
async def test_a_foreign_and_an_unknown_normalize_answer_the_same_body(
    client, accounts
):
    _, other = accounts
    theirs = await _own_corpus(other.id)

    foreign = await client.post(f"/simulate/normalize_graph?dataset_id={theirs}")
    unknown = await client.post(
        f"/simulate/normalize_graph?dataset_id={uuid.uuid4()}"
    )

    assert foreign.status_code == unknown.status_code == 404
    assert foreign.json() == unknown.json()


@requires_db
@pytest.mark.asyncio
async def test_an_unknown_normalize_is_404(client):
    response = await client.post(
        f"/simulate/normalize_graph?dataset_id={uuid.uuid4()}"
    )

    assert response.status_code == 404, response.text


@requires_db
@pytest.mark.asyncio
async def test_an_unknown_debate_graph_id_is_404(client):
    response = await client.post(
        "/simulate/debate",
        json={"query": QUERY, "graph_id": str(uuid.uuid4())},
    )

    assert response.status_code == 404, response.text


# --- the owner's own dataset is accepted --------------------------------------


@requires_db
@pytest.mark.asyncio
async def test_normalize_over_an_owned_dataset_is_accepted(client, accounts):
    owner, _ = accounts
    mine = await _own_corpus(owner.id)

    response = await client.post(f"/simulate/normalize_graph?dataset_id={mine}")

    assert response.status_code == 202, response.text


@requires_db
@pytest.mark.asyncio
async def test_ontology_accepts_a_fresh_corpus_without_writing_it(client):
    """The browser calls ontology before build_graph creates the row, so an unknown id passes."""
    fresh = uuid.uuid4()

    response = await client.post(f"/simulate/ontology?dataset_id={fresh}", json=[])

    assert response.status_code == 202, response.text
    assert await _row(fresh) is None
