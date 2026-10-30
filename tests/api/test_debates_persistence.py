"""Run-document persistence (rows are the truth) + the /simulate/debates routes.

The JSON mirror is retired: every doc write is an upsert of the run's head rows
(`jobs` + `runs`) and every streamed event its own `run_events` row. These
tests are the behavioral successors of the file-store suite.
"""

import asyncio
import os
import sys
import time
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

import src.api.debate_api as debate_api
import src.api.run_doc as run_doc
from src.api.debate_api import (
    _DEBATE_JOBS,
    _DEBATE_JOBS_LOCK,
    _DebateWSManager,
    _persist_debate_run,
    router,
)
from src.auth.deps import current_user
from src.db.engine import get_session_factory
from src.db.models import Job, Run, RunEvent, User

if sys.platform == "win32":
    # psycopg refuses to run async on the default ProactorEventLoop (same guard
    # as tests/api/test_auth_api.py).
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)

pytestmark = [requires_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def store_user(db):
    """The store's owner: every row these tests write belongs to this account.

    Deleting the account cascades its jobs/runs/events away.
    """
    factory = get_session_factory()
    async with factory() as session:
        user = User(
            email=f"run-truth-{uuid.uuid4().hex[:10]}@example.com",
            password_hash="not-a-real-hash",
        )
        session.add(user)
        await session.commit()
        account = SimpleNamespace(id=str(user.id))
    yield account
    async with factory() as session:
        await session.execute(delete(User).where(User.id == uuid.UUID(account.id)))
        await session.commit()


@pytest_asyncio.fixture
async def client(store_user):
    """The real router on both mounts (R15), the caller stubbed as the owner."""
    app = FastAPI()
    app.include_router(router)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(
        id=uuid.UUID(store_user.id)
    )
    transport = ASGITransport(app=app, client=("10.99.7.1", 5000))
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


@pytest.fixture
def writes(monkeypatch):
    """Record every head-row write while still writing for real."""
    calls: list[str] = []
    real_write = run_doc.write_run_doc

    async def spy(doc):
        calls.append(doc["run_id"])
        await real_write(doc)

    monkeypatch.setattr(run_doc, "write_run_doc", spy)
    return calls


@pytest.fixture
def fake_clock(monkeypatch):
    """The throttle's clock, advanced by hand — no real sleeping."""
    state = {"now": 10_000.0}
    monkeypatch.setattr(time, "monotonic", lambda: state["now"])
    return state


async def _register_job(
    run_id: str, manager: _DebateWSManager, user_id: str, status: str = "running"
) -> None:
    """A live job AND its rows — as `create_debate` leaves them."""
    _DEBATE_JOBS[run_id] = {
        "job_id": run_id,
        "user_id": user_id,
        "status": status,
        "query": "q",
        "graph_id": "ds-1",
        "config": {"max_rounds": 2},
        "created_at": "2026-10-02T10:00:00+00:00",
        "result": None,
        "error": None,
        "ws_manager": manager,
    }
    await run_doc.write_run_doc(debate_api._job_doc(_DEBATE_JOBS[run_id]))


def _stage_event(index: int) -> dict:
    return {"type": "stage", "stage": "round", "index": index}


def _doc(
    user_id: str,
    created_at: str,
    run_id: str | None = None,
    status: str = "complete",
    result: dict | None = None,
) -> dict:
    return {
        "run_id": run_id or str(uuid.uuid4()),
        "user_id": user_id,
        "created_at": created_at,
        "query": "question one",
        "dataset_id": "ds-1",
        "config": {"max_rounds": 2},
        "status": status,
        "events": [],
        "result": result,
    }


async def _event_rows(run_id: str) -> list[RunEvent]:
    async with get_session_factory()() as session:
        return (
            (
                await session.execute(
                    select(RunEvent)
                    .where(RunEvent.run_id == uuid.UUID(run_id))
                    .order_by(RunEvent.seq)
                )
            )
            .scalars()
            .all()
        )


async def test_debates_route_is_not_captured_by_job_id(client):
    """`/simulate/debates` must hit the list route, never `GET /simulate/{job_id}` (§12.4 warning)."""
    response = await client.get("/simulate/debates")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


async def test_list_is_newest_first(client, store_user):
    newer = _doc(store_user.id, "2026-10-02T10:00:00+00:00")
    older = _doc(store_user.id, "2026-10-01T10:00:00+00:00")
    await run_doc.write_run_doc(older)
    await run_doc.write_run_doc(newer)
    runs = (await client.get("/simulate/debates")).json()
    assert [run["run_id"] for run in runs] == [newer["run_id"], older["run_id"]]


async def test_summary_derives_verdict_stance_from_clusters(client, store_user):
    doc = _doc(
        store_user.id,
        "2026-10-01T10:00:00+00:00",
        result={
            "rounds_executed": 2,
            "converged": True,
            "cluster_details": {
                "POSITIVE": {"stance": "POSITIVE", "total_weight": 0.61},
                "NEGATIVE": {"stance": "NEGATIVE", "total_weight": 0.24},
            },
        },
    )
    await run_doc.write_run_doc(doc)
    run = (await client.get("/simulate/debates")).json()[0]
    assert run["verdict_stance"] == "POSITIVE"
    assert run["converged"] is True
    assert run["dataset_id"] == "ds-1"


async def test_summary_carries_the_filed_share(client, store_user):
    """The list must carry the filed share, so a list-driven surface never reads every run."""
    doc = _doc(
        store_user.id,
        "2026-10-01T10:00:00+00:00",
        result={
            "rounds_executed": 4,
            "converged": True,
            "confidence_score": 0.82,
            "cluster_details": {
                "NEGATIVE": {"stance": "NEGATIVE", "total_weight": 5.92},
                "POSITIVE": {"stance": "POSITIVE", "total_weight": 1.29},
            },
        },
    )
    await run_doc.write_run_doc(doc)
    run = (await client.get("/simulate/debates")).json()[0]
    assert run["verdict_confidence"] == 0.82


async def test_summary_share_is_null_when_no_answer_was_filed(client, store_user):
    doc = _doc(store_user.id, "2026-10-01T10:00:00+00:00", result={"rounds_executed": 1})
    await run_doc.write_run_doc(doc)
    run = (await client.get("/simulate/debates")).json()[0]
    assert run["verdict_confidence"] is None


async def test_run_doc_round_trip(client, store_user):
    doc = _doc(
        store_user.id,
        "2026-10-01T10:00:00+00:00",
        result={"rounds_executed": 2, "converged": True},
    )
    await run_doc.write_run_doc(doc)
    fetched = (await client.get(f"/simulate/debates/{doc['run_id']}")).json()
    assert fetched["query"] == "question one"
    assert fetched["events"] == []
    assert fetched["status"] == "complete"
    assert fetched["result"] == {"rounds_executed": 2, "converged": True}
    assert fetched["config"] == {"max_rounds": 2}


async def test_missing_run_doc_is_404(client, store_user):
    assert (await client.get("/simulate/debates/nope")).status_code == 404
    assert (await client.get(f"/simulate/debates/{uuid.uuid4()}")).status_code == 404


async def test_persist_debate_run_mirrors_the_live_job(store_user):
    run_id = str(uuid.uuid4())
    manager = _DebateWSManager(job_id=run_id)
    async with _DEBATE_JOBS_LOCK:
        await _register_job(run_id, manager, store_user.id)
    try:
        await manager.broadcast({"type": "stage", "stage": "intake", "index": 0})
        await _persist_debate_run(run_id)
        doc = await run_doc.read_run_doc(run_id)
        assert doc["events"][0]["stage"] == "intake"
        assert doc["status"] == "running"
        # R14: the creator's id rides the row, so ownership survives a restart.
        assert doc["user_id"] == store_user.id
    finally:
        async with _DEBATE_JOBS_LOCK:
            _DEBATE_JOBS.pop(run_id, None)


async def test_job_bound_manager_broadcast_persists_every_event(store_user):
    """A manager constructed WITH a job_id persists each broadcast as a row."""
    run_id = str(uuid.uuid4())
    manager = _DebateWSManager(job_id=run_id)
    async with _DEBATE_JOBS_LOCK:
        await _register_job(run_id, manager, store_user.id)
    try:
        for index in range(3):
            await manager.broadcast(_stage_event(index))
        rows = await _event_rows(run_id)
    finally:
        async with _DEBATE_JOBS_LOCK:
            _DEBATE_JOBS.pop(run_id, None)
    # seq 0 is the run_meta row; streamed events are monotonic from 1.
    assert [row.seq for row in rows] == [0, 1, 2, 3]
    assert [row.payload["index"] for row in rows[1:]] == [0, 1, 2]
    assert rows[1].type == "stage"


async def test_rapid_broadcasts_do_not_coalesce_events(store_user, writes, fake_clock):
    """Events are the durable record — each one is a row, never coalesced; the
    head write (status/result) is the throttled one."""
    run_id = str(uuid.uuid4())
    manager = _DebateWSManager(job_id=run_id)
    await _register_job(run_id, manager, store_user.id)
    writes.clear()  # registration wrote the rows; the window starts now
    try:
        for index in range(5):
            await manager.broadcast(_stage_event(index))
        assert writes == [run_id]  # one head write in the window

        fake_clock["now"] += 0.5
        await manager.broadcast(_stage_event(5))
        assert writes == [run_id, run_id]

        rows = await _event_rows(run_id)
        assert [row.payload["index"] for row in rows[1:]] == [0, 1, 2, 3, 4, 5]
    finally:
        _DEBATE_JOBS.pop(run_id, None)


async def test_throttle_is_keyed_per_run(store_user, writes, fake_clock):
    """Run B's head write is not throttled by run A's window."""
    run_a, run_b = str(uuid.uuid4()), str(uuid.uuid4())
    manager_a = _DebateWSManager(job_id=run_a)
    manager_b = _DebateWSManager(job_id=run_b)
    await _register_job(run_a, manager_a, store_user.id)
    await _register_job(run_b, manager_b, store_user.id)
    writes.clear()  # registrations wrote the rows; the window starts now
    try:
        await manager_a.broadcast(_stage_event(0))
        await manager_a.broadcast(_stage_event(1))  # head write coalesced
        await manager_b.broadcast(_stage_event(0))  # own window — writes
        assert writes == [run_a, run_b]
    finally:
        _DEBATE_JOBS.pop(run_a, None)
        _DEBATE_JOBS.pop(run_b, None)


@pytest.mark.parametrize("terminal_status", ["complete", "failed"])
async def test_terminal_status_write_bypasses_the_throttle(
    store_user, writes, fake_clock, terminal_status
):
    """The final head row is never stale, and the run's throttle state is dropped."""
    run_id = str(uuid.uuid4())
    manager = _DebateWSManager(job_id=run_id)
    await _register_job(run_id, manager, store_user.id)
    writes.clear()  # registration wrote the rows; the window starts now
    try:
        await manager.broadcast(_stage_event(0))
        await manager.broadcast(_stage_event(1))  # head write coalesced
        assert writes == [run_id]

        _DEBATE_JOBS[run_id]["status"] = terminal_status
        await manager.broadcast({"type": "complete"})
        assert writes == [run_id, run_id]

        doc = await run_doc.read_run_doc(run_id)
        assert doc["status"] == terminal_status
        assert len(doc["events"]) == 3
        assert run_id not in debate_api._LAST_PERSIST_AT
    finally:
        _DEBATE_JOBS.pop(run_id, None)


async def test_write_run_doc_is_idempotent(store_user):
    """Re-writing a doc upserts: one meta row, created_at and events survive."""
    doc = _doc(store_user.id, "2026-10-01T10:00:00+00:00")
    run_id = doc["run_id"]
    await run_doc.write_run_doc(doc)
    await run_doc.append_run_event(run_id, 1, {"type": "complete"})
    await run_doc.write_run_doc(
        {**doc, "status": "complete", "result": {"rounds_executed": 1}}
    )
    await run_doc.write_run_doc(
        {**doc, "status": "complete", "result": {"rounds_executed": 1}}
    )

    async with get_session_factory()() as session:
        meta_rows = (
            await session.execute(
                select(func.count())
                .select_from(RunEvent)
                .where(
                    RunEvent.run_id == uuid.UUID(run_id), RunEvent.type == "run_meta"
                )
            )
        ).scalar_one()
        run = await session.get(Run, uuid.UUID(run_id))
    assert meta_rows == 1
    assert run.created_at.isoformat().startswith("2026-10-01T10:00:00")

    fetched = await run_doc.read_run_doc(run_id)
    assert [event["type"] for event in fetched["events"]] == ["complete"]
    assert fetched["result"] == {"rounds_executed": 1}


async def test_head_rows_carry_the_job_state(store_user):
    doc = _doc(store_user.id, "2026-10-01T10:00:00+00:00", status="running")
    await run_doc.write_run_doc(doc)
    async with get_session_factory()() as session:
        job = await session.get(Job, uuid.UUID(doc["run_id"]))
    assert (job.kind, job.status, job.run_id) == (
        "debate",
        "running",
        uuid.UUID(doc["run_id"]),
    )
    assert job.started_at is not None and job.finished_at is None
