"""Task 5: rows are the run/job truth.

Status/list/get answer from Postgres — an in-process dict never does — and a
restart's "interrupted" state is derived from the boot sweep, not guessed from
dict membership.
"""

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
from sqlalchemy import delete, func, select

import src.api.api_server as api_server
import src.api.debate_api as debate_api
import src.api.run_doc as run_doc
from src.api.debate_api import router as debate_router
from src.auth.deps import current_user
from src.db.engine import get_session_factory
from src.jobs import queue as jobs_queue
from src.db.models import Dataset, Run, User

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)

pytestmark = [requires_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def accounts(db):
    """(owner, other) — two accounts; deleting them cascades their rows away."""
    factory = get_session_factory()
    made = []
    async with factory() as session:
        for _ in range(2):
            user = User(
                email=f"run-truth-{uuid.uuid4().hex[:10]}@example.com",
                password_hash="not-a-real-hash",
            )
            session.add(user)
            await session.commit()
            made.append(SimpleNamespace(id=str(user.id)))
    yield made
    async with factory() as session:
        for account in made:
            await session.execute(delete(User).where(User.id == uuid.UUID(account.id)))
        await session.commit()


def _app_for(account, *routers_with_prefixes) -> FastAPI:
    app = FastAPI()
    for router, prefix in routers_with_prefixes:
        app.include_router(router, prefix=prefix)
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(
        id=uuid.UUID(account.id), plan_key="free"
    )
    return app


@pytest_asyncio.fixture
async def client(accounts):
    """Both mounts (R15), routed to the debate + simulate routers."""
    owner, _ = accounts
    app = _app_for(
        owner,
        (debate_router, ""),
        (debate_router, "/api/v1"),
        (api_server.simulate_router, ""),
        (api_server.simulate_router, "/api/v1"),
    )
    transport = ASGITransport(app=app, client=("10.99.8.1", 5000))
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


def _job_doc(user_id: str, status: str = "queued", **extra) -> dict:
    doc = {
        "job_id": str(uuid.uuid4()),
        "user_id": user_id,
        "mode": "ontology",
        "status": status,
        "progress": 0.0,
        "stage": status,
        "error": None,
        "result": None,
    }
    doc.update(extra)
    return doc


def _run_doc(user_id: str, status: str = "queued", **extra) -> dict:
    doc = {
        "run_id": str(uuid.uuid4()),
        "user_id": user_id,
        "created_at": "2026-10-02T10:00:00+00:00",
        "query": "Should we expand into Europe?",
        "dataset_id": "ds-1",
        "config": {"max_rounds": 3},
        "status": status,
        "events": [],
        "result": None,
    }
    doc.update(extra)
    return doc


async def test_job_status_reads_from_rows_not_the_dict(client, accounts):
    owner, _ = accounts
    doc = _job_doc(owner.id, status="running", progress=0.42, stage="ontology_running")
    await run_doc.write_job_doc(doc)
    api_server.RUNS.pop(doc["job_id"], None)  # nothing in memory — the row answers

    response = await client.get(f"/simulate/jobs/{doc['job_id']}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "running"
    assert body["progress"] == 0.42
    assert body["stage"] == "ontology_running"
    assert body["mode"] == "ontology"


async def test_job_status_is_owner_only(client, accounts):
    owner, other = accounts
    doc = _job_doc(other.id, status="running")
    await run_doc.write_job_doc(doc)
    api_server.RUNS.pop(doc["job_id"], None)

    assert (await client.get(f"/simulate/jobs/{doc['job_id']}")).status_code == 404


async def test_run_status_reads_from_rows(client, accounts):
    owner, _ = accounts
    doc = _run_doc(owner.id)
    await run_doc.write_run_doc(doc)
    debate_api._DEBATE_JOBS.pop(doc["run_id"], None)  # nothing in memory

    response = await client.get(f"/simulate/{doc['run_id']}")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "queued"
    assert response.json()["job_id"] == doc["run_id"]


async def test_run_status_404_for_unknown_and_for_graph_jobs(client, accounts):
    owner, _ = accounts
    assert (await client.get(f"/simulate/{uuid.uuid4()}")).status_code == 404
    job = _job_doc(owner.id, status="running")
    await run_doc.write_job_doc(job)
    # A graph job is not a debate; `/simulate/{job_id}` must not answer for it.
    assert (await client.get(f"/simulate/{job['job_id']}")).status_code == 404


async def test_restart_sweep_marks_running_rows_interrupted(client, accounts):
    owner, _ = accounts
    run = _run_doc(owner.id, status="running")
    job = _job_doc(owner.id, status="running", mode="build_graph")
    await run_doc.write_run_doc(run)
    await run_doc.write_job_doc(job)

    swept = await run_doc.sweep_interrupted()

    assert swept >= 1
    status = (await client.get(f"/simulate/{run['run_id']}")).json()
    assert status["status"] == "failed"
    assert status["error"] == "interrupted"
    listing = (await client.get("/simulate/debates")).json()
    assert [item for item in listing if item["run_id"] == run["run_id"]][0][
        "status"
    ] == "interrupted"
    read_back = await run_doc.read_job_doc(job["job_id"])
    assert (read_back["status"], read_back["error"]) == ("failed", "interrupted")


async def test_completion_lands_verdict_and_confidence_on_the_runs_row(accounts):
    owner, _ = accounts
    result = {"rounds_executed": 2, "converged": True, "confidence_score": 0.77}
    doc = _run_doc(owner.id, status="complete", result=result)
    await run_doc.write_run_doc(doc)

    async with get_session_factory()() as session:
        row = (
            await session.execute(select(Run).where(Run.id == uuid.UUID(doc["run_id"])))
        ).scalar_one()
    assert row.verdict == result
    assert row.confidence == 0.77
    assert row.finished_at is not None


async def test_create_debate_persists_a_queued_row_at_accept(
    client, accounts, monkeypatch
):
    owner, _ = accounts
    monkeypatch.setattr(debate_api, "_run_debate_async", AsyncMock())

    response = await client.post(
        "/simulate/debate", json={"query": "Should we tax carbon?", "graph_id": "ds-1"}
    )

    assert response.status_code == 202, response.text
    run_id = response.json()["job_id"]
    head = await run_doc.read_run_head(run_id)
    assert head is not None
    assert (head["status"], head["user_id"]) == ("queued", owner.id)
    debate_api._DEBATE_JOBS.pop(run_id, None)


async def test_debate_over_an_owned_corpus_persists_its_corpus(
    client, accounts, monkeypatch
):
    """`runs.dataset_id` is a foreign key: the queued row may only point at a row
    the caller owns. This is the golden path's 500 — a corpus built fresh had no
    `datasets` row, so the insert violated the constraint after the 202 path."""
    owner, _ = accounts
    monkeypatch.setattr(debate_api, "_run_debate_async", AsyncMock())
    # The rows are the subject; nothing may actually run (no worker, no LLM).
    monkeypatch.setattr(jobs_queue, "_dispatch", lambda *args: None)
    corpus = uuid.uuid4()
    async with get_session_factory()() as session:
        session.add(
            Dataset(id=corpus, user_id=uuid.UUID(owner.id), name="Mill Street")
        )
        await session.commit()

    response = await client.post(
        "/simulate/debate",
        json={
            "query": "Should we open a second location?",
            "graph_id": str(corpus),
            "corpus_label": "Mill Street",
        },
    )

    assert response.status_code == 202, response.text
    run_id = response.json()["job_id"]
    async with get_session_factory()() as session:
        row = await session.get(Run, uuid.UUID(run_id))
    assert row is not None
    assert row.dataset_id == corpus
    assert row.corpus_label == "Mill Street"
    debate_api._DEBATE_JOBS.pop(run_id, None)


async def test_a_corpus_owned_by_someone_else_is_the_uniform_404(
    client, accounts, monkeypatch
):
    _, other = accounts
    monkeypatch.setattr(debate_api, "_run_debate_async", AsyncMock())
    corpus = uuid.uuid4()
    async with get_session_factory()() as session:
        session.add(Dataset(id=corpus, user_id=uuid.UUID(other.id), name="Theirs"))
        await session.commit()

    response = await client.post(
        "/simulate/debate",
        json={"query": "Should we expand?", "graph_id": str(corpus)},
    )

    assert response.status_code == 404
    async with get_session_factory()() as session:
        count = await session.scalar(
            select(func.count()).select_from(Run).where(Run.dataset_id == corpus)
        )
    assert count == 0
