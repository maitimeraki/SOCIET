"""Run-document persistence + the /simulate/debates routes (route order guarded)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.run_doc as run_doc
from src.api.debate_api import _DEBATE_JOBS, _DEBATE_JOBS_LOCK, _DebateWSManager, _persist_debate_run, router


@pytest.fixture
def store_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(run_doc, "RUNS_DIR", tmp_path / "debates")
    return tmp_path / "debates"


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
    runs = client.get("/simulate/debates").json()
    assert [run["run_id"] for run in runs] == ["r1"]


def test_missing_run_doc_is_404(client, store_dir):
    assert client.get("/simulate/debates/nope").status_code == 404


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
    """A manager constructed WITH a job_id auto-persists on every broadcast (§12.4)."""
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
