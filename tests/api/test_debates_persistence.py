"""Run-document persistence + the /simulate/debates routes (route order guarded)."""
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.debate_api as debate_api
import src.api.run_doc as run_doc
from src.api.debate_api import _DEBATE_JOBS, _DEBATE_JOBS_LOCK, _DebateWSManager, _persist_debate_run, router


@pytest.fixture
def store_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(run_doc, "RUNS_DIR", tmp_path / "debates")
    return tmp_path / "debates"


@pytest.fixture
def writes(monkeypatch, store_dir):
    """Record every run-doc write while still writing for real."""
    calls: list[str] = []
    real_write = run_doc.write_run_doc

    def spy(doc):
        calls.append(doc["run_id"])
        real_write(doc)

    monkeypatch.setattr(run_doc, "write_run_doc", spy)
    return calls


@pytest.fixture
def fake_clock(monkeypatch):
    """The throttle's clock, advanced by hand — no real sleeping."""
    state = {"now": 10_000.0}
    monkeypatch.setattr(time, "monotonic", lambda: state["now"])
    return state


def _register_job(run_id: str, manager: _DebateWSManager, status: str = "running") -> None:
    _DEBATE_JOBS[run_id] = {
        "job_id": run_id, "status": status, "query": "q", "graph_id": "ds-1",
        "config": {"max_rounds": 2}, "created_at": "2026-10-02T10:00:00+00:00",
        "result": None, "error": None, "ws_manager": manager,
    }


def _stage_event(index: int) -> dict:
    return {"type": "stage", "stage": "round", "index": index}


@pytest.fixture
def client():
    """Real app wrapper: a bare router cannot serve requests (FastAPI >=0.135)."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _doc(run_id: str, created_at: str, status: str = "complete", result: dict | None = None) -> dict:
    return {
        "run_id": run_id,
        "created_at": created_at,
        "query": f"question {run_id}",
        "dataset_id": "ds-1",
        "config": {"max_rounds": 2},
        "status": status,
        "events": [],
        "result": result,
    }


def test_debates_route_is_not_captured_by_job_id(client, store_dir):
    """`/simulate/debates` must hit the list route, never `GET /simulate/{job_id}` (§12.4 warning)."""
    response = client.get("/simulate/debates")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_list_is_newest_first(client, store_dir):
    run_doc.write_run_doc(_doc("r1", "2026-10-01T10:00:00+00:00"))
    run_doc.write_run_doc(_doc("r2", "2026-10-02T10:00:00+00:00"))
    runs = client.get("/simulate/debates").json()
    assert [run["run_id"] for run in runs] == ["r2", "r1"]


def test_summary_derives_verdict_stance_from_clusters(client, store_dir):
    run_doc.write_run_doc(
        _doc("r1", "2026-10-01T10:00:00+00:00", result={
            "rounds_executed": 2, "converged": True,
            "cluster_details": {
                "POSITIVE": {"stance": "POSITIVE", "total_weight": 0.61},
                "NEGATIVE": {"stance": "NEGATIVE", "total_weight": 0.24},
            },
        })
    )
    run = client.get("/simulate/debates").json()[0]
    assert run["verdict_stance"] == "POSITIVE"
    assert run["converged"] is True


def test_stale_running_doc_reads_as_interrupted(client, store_dir):
    """A `running` doc with no live in-memory job means the server restarted (§7.10) — say so."""
    run_doc.write_run_doc(_doc("r1", "2026-10-01T10:00:00+00:00", status="running"))
    assert client.get("/simulate/debates").json()[0]["status"] == "interrupted"


def test_run_doc_round_trip(client, store_dir):
    run_doc.write_run_doc(_doc("r1", "2026-10-01T10:00:00+00:00", result={"rounds_executed": 2, "converged": True}))
    fetched = client.get("/simulate/debates/r1").json()
    assert fetched["query"] == "question r1"
    assert fetched["events"] == []
    assert fetched["status"] == "complete"
    assert fetched["result"] == {"rounds_executed": 2, "converged": True}


def test_list_skips_corrupt_docs(client, store_dir):
    run_doc.write_run_doc(_doc("r1", "2026-10-01T10:00:00+00:00"))
    (store_dir / "broken.json").write_text("{ not json", encoding="utf-8")
    (store_dir / "null.json").write_text("null", encoding="utf-8")
    (store_dir / "badbytes.json").write_bytes(b"\xff\xfe\x00")
    runs = client.get("/simulate/debates").json()
    assert [run["run_id"] for run in runs] == ["r1"]


def test_missing_run_doc_is_404(client, store_dir):
    assert client.get("/simulate/debates/nope").status_code == 404


def test_corrupt_run_doc_reads_as_missing_not_a_crash(client, store_dir):
    """A corrupt single run doc degrades to 404, matching `list_run_docs`, which
    already skips unreadable files — the singular read must not raise instead."""
    store_dir.mkdir(parents=True, exist_ok=True)
    (store_dir / "corrupt.json").write_text("{ not json", encoding="utf-8")
    assert client.get("/simulate/debates/corrupt").status_code == 404


@pytest.mark.asyncio
async def test_persist_debate_run_mirrors_the_live_job(store_dir):
    manager = _DebateWSManager()
    async with _DEBATE_JOBS_LOCK:
        _DEBATE_JOBS["job-x"] = {
            "job_id": "job-x", "status": "running", "query": "q", "graph_id": "ds-1",
            "config": {"max_rounds": 2}, "created_at": "2026-10-02T10:00:00+00:00",
            "result": None, "error": None, "ws_manager": manager,
        }
    try:
        await manager.broadcast({"type": "stage", "stage": "intake", "index": 0})
        await _persist_debate_run("job-x")
        doc = run_doc.read_run_doc("job-x")
        assert doc["events"][0]["stage"] == "intake"
        assert doc["status"] == "running"
    finally:
        async with _DEBATE_JOBS_LOCK:
            _DEBATE_JOBS.pop("job-x", None)


@pytest.mark.asyncio
async def test_job_bound_manager_broadcast_persists(store_dir):
    """A manager constructed WITH a job_id auto-persists on broadcast (§12.4)."""
    manager = _DebateWSManager(job_id="job-y")
    async with _DEBATE_JOBS_LOCK:
        _DEBATE_JOBS["job-y"] = {
            "job_id": "job-y", "status": "running", "query": "q", "graph_id": "ds-1",
            "config": {"max_rounds": 2}, "created_at": "2026-10-02T10:00:00+00:00",
            "result": None, "error": None, "ws_manager": manager,
        }
    try:
        await manager.broadcast({"type": "stage", "stage": "intake", "index": 0})
        doc = run_doc.read_run_doc("job-y")
    finally:
        async with _DEBATE_JOBS_LOCK:
            _DEBATE_JOBS.pop("job-y", None)
    assert doc is not None
    assert doc["events"][0]["stage"] == "intake"
    assert doc["status"] == "running"


@pytest.mark.asyncio
async def test_rapid_broadcasts_coalesce_to_one_write_per_window(store_dir, writes, fake_clock):
    """Events inside the 0.5 s window are skipped; the next write carries the full state."""
    manager = _DebateWSManager(job_id="job-throttle")
    _register_job("job-throttle", manager)
    try:
        for index in range(5):
            await manager.broadcast(_stage_event(index))
        assert writes == ["job-throttle"]

        fake_clock["now"] += 0.5
        await manager.broadcast(_stage_event(5))
        assert writes == ["job-throttle", "job-throttle"]

        doc = run_doc.read_run_doc("job-throttle")
        assert [event["index"] for event in doc["events"]] == [0, 1, 2, 3, 4, 5]
    finally:
        _DEBATE_JOBS.pop("job-throttle", None)


@pytest.mark.asyncio
async def test_throttle_is_keyed_per_run(store_dir, writes, fake_clock):
    """Run B's broadcast is not throttled by run A's window."""
    manager_a = _DebateWSManager(job_id="job-run-a")
    manager_b = _DebateWSManager(job_id="job-run-b")
    _register_job("job-run-a", manager_a)
    _register_job("job-run-b", manager_b)
    try:
        await manager_a.broadcast(_stage_event(0))
        await manager_a.broadcast(_stage_event(1))  # coalesced
        await manager_b.broadcast(_stage_event(0))  # own window — writes
        assert writes == ["job-run-a", "job-run-b"]
    finally:
        _DEBATE_JOBS.pop("job-run-a", None)
        _DEBATE_JOBS.pop("job-run-b", None)


@pytest.mark.parametrize("terminal_status", ["complete", "failed"])
@pytest.mark.asyncio
async def test_terminal_status_write_bypasses_the_throttle(store_dir, writes, fake_clock, terminal_status):
    """The final doc on disk is never stale, and the run's throttle state is dropped."""
    manager = _DebateWSManager(job_id="job-terminal")
    _register_job("job-terminal", manager)
    try:
        await manager.broadcast(_stage_event(0))
        await manager.broadcast(_stage_event(1))  # coalesced
        assert writes == ["job-terminal"]

        _DEBATE_JOBS["job-terminal"]["status"] = terminal_status
        await manager.broadcast({"type": "complete"})
        assert writes == ["job-terminal", "job-terminal"]

        doc = run_doc.read_run_doc("job-terminal")
        assert doc["status"] == terminal_status
        assert len(doc["events"]) == 3
        assert "job-terminal" not in debate_api._LAST_PERSIST_AT
    finally:
        _DEBATE_JOBS.pop("job-terminal", None)


def test_written_run_doc_is_compact_json(store_dir):
    """Machine-read, not human-diffed: no indent whitespace on disk."""
    doc = _doc("r-compact", "2026-10-01T10:00:00+00:00", result={"rounds_executed": 2})
    run_doc.write_run_doc(doc)
    raw = (store_dir / "r-compact.json").read_text(encoding="utf-8")
    assert "\n" not in raw
    assert json.loads(raw) == doc
