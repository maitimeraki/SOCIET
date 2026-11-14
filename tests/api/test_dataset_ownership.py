"""Audit C1 (fixes 5, 6): a graph route takes only a UUID dataset id, and the caller owns it.

A non-uuid id (the old shared ``simulation_runtime`` default) is refused before any
handler runs. Every graph route that takes a dataset id claims or checks it through
one rule: an unknown corpus is registered to the caller, a corpus owned by someone
else is the same 404 as a missing one, and that 404 comes before any reservation,
enqueue, run row or metered call.

Most cases below stub the seams (the ownership helper, the reservation, the enqueue,
the entitlements) so they run without a database; the DB-backed cases at the bottom
exercise the real rows and skip when DATABASE_URL is unset.
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
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

import src.api.api_server as api_server
import src.api.debate_api as debate_api
from src.api.api_server import simulate_router
from src.api.debate_api import router as debate_router
from src.api.limits import install_rate_limiter
from src.auth.deps import current_user, require_owned_dataset
from src.billing import units as billing_units
from src.db.engine import get_db, get_session_factory
from src.db.models import Dataset, Job, Run, User
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
    """The real routers with the raw FastAPI error body (``{"detail": ...}``)."""
    app = FastAPI()
    install_rate_limiter(app)
    app.include_router(simulate_router)
    app.include_router(debate_router)
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(
        id=user_id, plan_key="free"
    )
    return app


def _reservation():
    return SimpleNamespace(
        amount=0, period_start=datetime.datetime.now(datetime.UTC)
    )


async def _refuse(*_args, **_kwargs):
    raise HTTPException(status_code=404, detail="Not found.")


class _Rows:
    """A database stand-in for `db.get`, so the ownership rule runs without Postgres."""

    def __init__(self, *rows):
        self._by_id = {row.id: row for row in rows}

    async def get(self, _model, key):
        return self._by_id.get(key)


@pytest_asyncio.fixture
async def bare_client(monkeypatch):
    """Reaches the routes with no account, no session and no database."""
    monkeypatch.setattr(
        api_server, "enqueue_or_http", AsyncMock(return_value="job-bare")
    )
    monkeypatch.setattr(
        api_server, "_reserve_graph_job", AsyncMock(return_value=_reservation())
    )
    app = _app(uuid.uuid4())

    async def _no_session():
        yield None

    app.dependency_overrides[get_db] = _no_session
    transport = ASGITransport(app=app, client=("10.99.9.2", 5000))
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


# --- the ownership rule itself (no database) ----------------------------------


@pytest.mark.asyncio
async def test_the_owned_corpus_is_returned():
    owner = uuid.uuid4()
    row = SimpleNamespace(id=uuid.uuid4(), user_id=owner)

    found = await require_owned_dataset(_Rows(row), SimpleNamespace(id=owner), row.id)

    assert found is row


@pytest.mark.asyncio
async def test_an_unknown_corpus_is_404_not_found():
    with pytest.raises(HTTPException) as refused:
        await require_owned_dataset(
            _Rows(), SimpleNamespace(id=uuid.uuid4()), uuid.uuid4()
        )

    assert (refused.value.status_code, refused.value.detail) == (404, "Not found.")


@pytest.mark.asyncio
async def test_a_foreign_corpus_is_the_same_404_as_an_unknown_one():
    owner, caller = uuid.uuid4(), uuid.uuid4()
    row = SimpleNamespace(id=uuid.uuid4(), user_id=owner)

    with pytest.raises(HTTPException) as refused:
        await require_owned_dataset(_Rows(row), SimpleNamespace(id=caller), row.id)

    assert (refused.value.status_code, refused.value.detail) == (404, "Not found.")


# --- a non-uuid dataset id never reaches a handler ----------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("path", GRAPH_ROUTES)
async def test_a_non_uuid_dataset_is_refused_on_graph_routes(bare_client, path):
    response = await bare_client.post(f"{path}?dataset_id=simulation_runtime", json=[])

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


# --- one claim-or-owner rule, decided before any side effect (no database) ----


@pytest.mark.asyncio
async def test_ontology_claims_its_corpus_through_the_build_path(
    bare_client, monkeypatch
):
    claimed = []

    async def _claim(_db, _user, dataset_id, name):
        claimed.append((dataset_id, name))

    monkeypatch.setattr(api_server, "_register_corpus", _claim)
    corpus = uuid.uuid4()

    response = await bare_client.post(f"/simulate/ontology?dataset_id={corpus}", json=[])

    assert response.status_code == 202, response.text
    assert claimed == [(corpus, "")]


@pytest.mark.asyncio
async def test_ontology_refuses_a_foreign_corpus_before_reservation_or_enqueue(
    bare_client, monkeypatch
):
    monkeypatch.setattr(api_server, "_register_corpus", _refuse)
    reserve = AsyncMock(return_value=_reservation())
    enqueue = AsyncMock(return_value="job")
    monkeypatch.setattr(api_server, "_reserve_graph_job", reserve)
    monkeypatch.setattr(api_server, "enqueue_or_http", enqueue)

    response = await bare_client.post(
        f"/simulate/ontology?dataset_id={uuid.uuid4()}", json=[]
    )

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Not found."
    reserve.assert_not_awaited()
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_build_refuses_a_foreign_corpus_before_reservation_or_enqueue(
    bare_client, monkeypatch
):
    monkeypatch.setattr(api_server, "_register_corpus", _refuse)
    reserve = AsyncMock(return_value=_reservation())
    enqueue = AsyncMock(return_value="job")
    monkeypatch.setattr(api_server, "_reserve_graph_job", reserve)
    monkeypatch.setattr(api_server, "enqueue_or_http", enqueue)

    response = await bare_client.post(
        f"/simulate/build_graph?dataset_id={uuid.uuid4()}", json=[]
    )

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Not found."
    reserve.assert_not_awaited()
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_normalize_refuses_an_unowned_corpus_before_reservation_or_enqueue(
    bare_client, monkeypatch
):
    monkeypatch.setattr(api_server, "require_owned_dataset", _refuse)
    reserve = AsyncMock(return_value=_reservation())
    enqueue = AsyncMock(return_value="job")
    monkeypatch.setattr(api_server, "_reserve_graph_job", reserve)
    monkeypatch.setattr(api_server, "enqueue_or_http", enqueue)

    response = await bare_client.post(
        f"/simulate/normalize_graph?dataset_id={uuid.uuid4()}"
    )

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Not found."
    reserve.assert_not_awaited()
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_debate_refuses_an_unowned_corpus_before_entitlements_units_or_enqueue(
    bare_client, monkeypatch
):
    monkeypatch.setattr(debate_api, "require_owned_dataset", _refuse)
    entitlements = AsyncMock()
    reserve = AsyncMock()
    enqueue = AsyncMock(return_value="job")
    monkeypatch.setattr(debate_api, "resolve_entitlements", entitlements)
    monkeypatch.setattr(billing_units, "reserve_units", reserve)
    monkeypatch.setattr(debate_api, "enqueue_or_http", enqueue)

    response = await bare_client.post(
        "/simulate/debate",
        json={"query": QUERY, "graph_id": str(uuid.uuid4())},
    )

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Not found."
    entitlements.assert_not_awaited()
    reserve.assert_not_awaited()
    enqueue.assert_not_awaited()


# --- the database-backed cases (skip without DATABASE_URL) ---------------------


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
    monkeypatch.setattr(
        api_server, "_reserve_graph_job", AsyncMock(return_value=_reservation())
    )
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


async def _count(model, user_id: uuid.UUID) -> int:
    async with get_session_factory()() as session:
        return await session.scalar(
            select(func.count()).select_from(model).where(model.user_id == user_id)
        )


async def _post_graph_route(http, path: str, dataset_id: str):
    if path == "/simulate/normalize_graph":
        return await http.post(f"{path}?dataset_id={dataset_id}")
    return await http.post(f"{path}?dataset_id={dataset_id}", json=[])


@requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize("path", GRAPH_ROUTES)
async def test_a_foreign_dataset_is_the_uniform_404(client, accounts, path):
    owner, other = accounts
    theirs = await _own_corpus(other.id)

    response = await _post_graph_route(client, path, str(theirs))

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Not found."
    assert await _count(Job, owner.id) == 0


@requires_db
@pytest.mark.asyncio
async def test_a_foreign_debate_graph_id_is_the_uniform_404_with_no_run_or_job(
    client, accounts
):
    owner, other = accounts
    theirs = await _own_corpus(other.id)

    response = await client.post(
        "/simulate/debate", json={"query": QUERY, "graph_id": str(theirs)}
    )

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Not found."
    assert await _count(Run, owner.id) == 0
    assert await _count(Job, owner.id) == 0


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
    response = await client.post(f"/simulate/normalize_graph?dataset_id={uuid.uuid4()}")

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Not found."


@requires_db
@pytest.mark.asyncio
async def test_an_unknown_debate_graph_id_is_404(client):
    response = await client.post(
        "/simulate/debate",
        json={"query": QUERY, "graph_id": str(uuid.uuid4())},
    )

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Not found."


@requires_db
@pytest.mark.asyncio
async def test_normalize_over_an_owned_dataset_is_accepted(client, accounts):
    owner, _ = accounts
    mine = await _own_corpus(owner.id)

    response = await client.post(f"/simulate/normalize_graph?dataset_id={mine}")

    assert response.status_code == 202, response.text


@requires_db
@pytest.mark.asyncio
async def test_ontology_registers_a_fresh_corpus_to_its_caller(client, accounts):
    """Ontology is the first call for a new corpus: it claims the row for the caller."""
    owner, _ = accounts
    fresh = uuid.uuid4()

    response = await client.post(f"/simulate/ontology?dataset_id={fresh}", json=[])

    assert response.status_code == 202, response.text
    row = await _row(fresh)
    assert row is not None
    assert row.user_id == owner.id
