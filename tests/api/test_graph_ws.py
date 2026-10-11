"""Task 9 — WebSocket route: snapshot, deltas, vocabulary (R14 late-client).

The route is the only graph-state channel for the UI. Frame order on connect:
`snapshot` first (so a late client gets the full stored graph before the live
stream), then `delta` frames, a `vocabulary` frame whenever a delta introduces
new labels, then `done` at a terminal job status.

R14: `subscribe` is only terminated by a `close()` sentinel, and `close()` only
reaches queues registered at close time — so a client that connects AFTER the
job finished must still be served (snapshot then done) without hanging. These
tests drive `publish` on the app's own loop (via a `call_later` timer inside the
stubbed `read_snapshot`) so no cross-thread queue access is involved.
"""
import asyncio
import threading
import uuid

import pytest
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient

import src.api.graph_snapshot as graph_snapshot
from src.api import api_server, graph_stream
from src.api.graph_stream import GraphDelta
from src.api.graph_stream_api import _drain_queued, router


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def _collect(client: TestClient, url: str, count: int, timeout: float = 5.0) -> list[dict]:
    """Read `count` WS frames, but fail loudly instead of hanging if the route
    never produces them (an R14 regression would otherwise block forever)."""
    box: dict = {}

    def _run() -> None:
        try:
            with client.websocket_connect(url) as ws:
                box["frames"] = [ws.receive_json() for _ in range(count)]
        except Exception as exc:  # surfaced on the test thread below
            box["error"] = exc

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=timeout)
    assert not thread.is_alive(), f"route produced no frame within {timeout}s (hung)"
    if "error" in box:
        raise box["error"]
    return box["frames"]


@pytest.fixture(autouse=True)
def _clean_runs():
    before = set(api_server.RUNS)
    yield
    for job_id in set(api_server.RUNS) - before:
        api_server.RUNS.pop(job_id, None)


def test_first_frame_is_snapshot_then_deltas_vocabulary_and_done(monkeypatch):
    job_id = f"ws-{uuid.uuid4()}"
    api_server.RUNS[job_id] = {"status": "running", "result": {"dataset_id": "ds-1"}}

    def _emit_after_subscribe() -> None:
        # Runs on the app loop 50ms after the snapshot is read, i.e. after the
        # route has subscribed — same loop, so `publish` is thread-safe.
        graph_stream.publish(job_id, GraphDelta(
            nodes=[{"id": "Person:Alice", "label": "Alice", "type": "PERSON"}],
            edges=[{"source": "Person:Alice", "target": "Person:Alice", "label": "RELATED_TO"}],
            new_labels=["PERSON"], chunk_id="c0", progress=0.5,
        ))
        graph_stream.publish(job_id, GraphDelta(
            nodes=[{"id": "Org:Acme", "label": "Acme", "type": "ORG"}],
            edges=[], new_labels=[], chunk_id="c1", progress=1.0,
        ))
        api_server.RUNS[job_id]["status"] = "completed"

    async def fake_snapshot(dataset_id: str) -> GraphDelta:
        assert dataset_id == "ds-1"
        asyncio.get_running_loop().call_later(0.05, _emit_after_subscribe)
        return GraphDelta(
            nodes=[{"id": "Person:Seed", "label": "Seed", "type": "PERSON"}],
            edges=[], new_labels=["PERSON", "ORG"],
        )

    monkeypatch.setattr(graph_snapshot, "read_snapshot", fake_snapshot)

    frames = _collect(TestClient(_app()), f"/simulate/{job_id}/graph_stream", count=5)

    assert [f["type"] for f in frames] == ["snapshot", "delta", "vocabulary", "delta", "done"]
    assert frames[0] == {
        "type": "snapshot",
        "nodes": [{"id": "Person:Seed", "label": "Seed", "type": "PERSON"}],
        "edges": [],
        "labels": ["PERSON", "ORG"],  # labels field rebuilds the legend on reconnect
    }
    assert frames[1]["chunk_id"] == "c0"
    assert frames[1]["nodes"] == [{"id": "Person:Alice", "label": "Alice", "type": "PERSON"}]
    assert frames[1]["progress"] == 0.5
    assert frames[2] == {"type": "vocabulary", "labels": ["PERSON"], "chunk_id": "c0"}
    assert frames[3]["chunk_id"] == "c1"
    assert frames[4] == {"type": "done"}


def test_late_client_after_completion_gets_snapshot_then_done(monkeypatch):
    """R14: the sentinel-only path would strand this client forever."""
    job_id = f"ws-{uuid.uuid4()}"
    api_server.RUNS[job_id] = {"status": "completed", "result": {"dataset_id": "ds-done"}}

    async def fake_snapshot(dataset_id: str) -> GraphDelta:
        assert dataset_id == "ds-done"
        return GraphDelta(
            nodes=[{"id": "Person:Alice", "label": "Alice", "type": "PERSON"}],
            edges=[], new_labels=["PERSON"],
        )

    monkeypatch.setattr(graph_snapshot, "read_snapshot", fake_snapshot)

    frames = _collect(TestClient(_app()), f"/simulate/{job_id}/graph_stream", count=2)

    assert frames[0]["type"] == "snapshot"
    assert frames[0]["labels"] == ["PERSON"]
    assert frames[1] == {"type": "done"}


@pytest.mark.asyncio
async def test_drain_queued_delivers_a_delta_ready_on_the_terminal_tick():
    """The terminal poll can win the race just before `__anext__` yields a delta
    published on the same tick; the drain must still forward it before `done`."""

    class _WS:
        def __init__(self) -> None:
            self.frames: list[dict] = []

        async def send_json(self, payload: dict) -> None:
            self.frames.append(payload)

    class _Sub:
        """Yields one delta, then behaves like an exhausted subscription."""

        def __init__(self) -> None:
            self._items = [GraphDelta(nodes=[{"id": "P", "label": "P", "type": "T"}], chunk_id="c-term")]

        async def __anext__(self) -> GraphDelta:
            if self._items:
                return self._items.pop(0)
            raise StopAsyncIteration

    sub = _Sub()
    ws = _WS()
    # The in-flight `__anext__` that is already resolved when the poll fires.
    pending = asyncio.create_task(sub.__anext__())

    pending = await _drain_queued(ws, sub, pending)

    assert [f["type"] for f in ws.frames] == ["delta"]
    assert ws.frames[0]["chunk_id"] == "c-term"
    await asyncio.gather(pending, return_exceptions=True)  # exhausted successor, retrieve it


def test_delta_published_during_the_snapshot_window_is_delivered_once(monkeypatch):
    """I3: the subscription is registered (its first `__anext__` primed) BEFORE the
    snapshot is read, so a delta published while the snapshot is built is queued —
    not lost in the read→subscribe gap — and de-duplicated against the snapshot so a
    node carried by both is delivered exactly once."""
    job_id = f"ws-{uuid.uuid4()}"
    api_server.RUNS[job_id] = {"status": "running", "result": {"dataset_id": "ds-gap"}}

    async def fake_snapshot(dataset_id: str) -> GraphDelta:
        assert dataset_id == "ds-gap"
        # Stands in for the real read's thread hop: yield once so the route's primed
        # `__anext__` registers the queue before this publish lands on it.
        await asyncio.sleep(0)
        graph_stream.publish(job_id, GraphDelta(
            nodes=[
                {"id": "Person:Seed", "label": "Seed", "type": "PERSON"},  # snapshot already carries it
                {"id": "Org:New", "label": "New", "type": "ORG"},          # written after the read began
            ],
            edges=[{"source": "Person:Seed", "target": "Org:New", "label": "WORKS_AT"}],
            new_labels=["ORG"], chunk_id="c-gap", progress=0.4,
        ))
        api_server.RUNS[job_id]["status"] = "completed"  # let the stream terminate
        return GraphDelta(
            nodes=[{"id": "Person:Seed", "label": "Seed", "type": "PERSON"}],
            edges=[], new_labels=["PERSON"],
        )

    monkeypatch.setattr(graph_snapshot, "read_snapshot", fake_snapshot)

    frames = _collect(TestClient(_app()), f"/simulate/{job_id}/graph_stream", count=4)

    assert [f["type"] for f in frames] == ["snapshot", "delta", "vocabulary", "done"]
    # The snapshot is still the FIRST frame, and unchanged.
    assert frames[0]["nodes"] == [{"id": "Person:Seed", "label": "Seed", "type": "PERSON"}]
    # The gap delta arrives after it; the node the snapshot already had is dropped,
    # the node written after the read began is kept.
    assert frames[1]["nodes"] == [{"id": "Org:New", "label": "New", "type": "ORG"}]
    assert frames[1]["edges"] == [{"source": "Person:Seed", "target": "Org:New", "label": "WORKS_AT"}]
    assert frames[1]["progress"] == 0.4
    assert frames[2] == {"type": "vocabulary", "labels": ["ORG"], "chunk_id": "c-gap"}
    # Exactly once: Person:Seed is delivered by the snapshot alone, never twice.
    delivered = [n["id"] for f in frames for n in f.get("nodes", [])]
    assert delivered.count("Person:Seed") == 1
    assert delivered.count("Org:New") == 1


class _DisconnectingWS:
    """A socket whose peer has already gone: every send raises, exactly as it does
    when a client closes during the snapshot window (reload, StrictMode remount,
    navigation). No receive side is reached — the route returns before streaming."""

    async def accept(self) -> None:
        pass

    async def send_json(self, payload: dict) -> None:
        raise WebSocketDisconnect(code=1006)


@pytest.mark.asyncio
async def test_disconnect_during_snapshot_window_does_not_escape_the_route(monkeypatch):
    """The reported failure: a client that closed while the snapshot was being read
    made the snapshot send raise `WebSocketDisconnect` straight out of the ASGI app
    (uvicorn logged a full `Exception in ASGI application`). The route must absorb it
    and return cleanly, dropping the subscription."""
    job_id = f"ws-{uuid.uuid4()}"
    api_server.RUNS[job_id] = {"status": "running", "result": {"dataset_id": "ds-gone"}}

    async def fake_snapshot(dataset_id: str) -> GraphDelta:
        return GraphDelta(nodes=[], edges=[], new_labels=[])

    monkeypatch.setattr(graph_snapshot, "read_snapshot", fake_snapshot)
    from src.api.graph_stream_api import stream_graph

    await stream_graph(_DisconnectingWS(), job_id)  # must return, not raise


@pytest.mark.asyncio
async def test_disconnect_on_unknown_job_done_send_does_not_escape():
    """Same class of hang-up on the other pre-stream send: the `done` frame for a
    job with no dataset. That send sits outside the streaming try, so it needs the
    guard too."""
    job_id = f"ws-{uuid.uuid4()}"  # never registered: _job_state -> ("failed", None)
    from src.api.graph_stream_api import stream_graph

    await stream_graph(_DisconnectingWS(), job_id)  # must return, not raise


class _RecordingWS:
    """A live socket: sends are recorded so a test can assert the frames emitted."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def accept(self) -> None:
        pass

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_snapshot_read_failure_is_reported_and_does_not_escape(monkeypatch):
    """A data-retrieval failure AFTER accept — Neo4j unreachable while reading the
    snapshot — must not escape as an ASGI exception (the HTTP global handler does
    not cover WebSockets). It is reported as an `error` frame, then `done`."""
    job_id = f"ws-{uuid.uuid4()}"
    api_server.RUNS[job_id] = {"status": "running", "result": {"dataset_id": "ds-boom"}}

    async def boom(dataset_id: str) -> GraphDelta:
        raise RuntimeError("neo4j unreachable")

    monkeypatch.setattr(graph_snapshot, "read_snapshot", boom)
    from src.api.graph_stream_api import stream_graph

    ws = _RecordingWS()
    await stream_graph(ws, job_id)  # must return, not raise

    assert [f["type"] for f in ws.sent] == ["error", "done"]
    assert "neo4j unreachable" in ws.sent[0]["message"]
