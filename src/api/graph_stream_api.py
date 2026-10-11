"""Task 9 — the live-graph WebSocket route.

One channel carries the whole live graph so the UI never polls REST for graph
state. On connect a client gets a `snapshot` (the full stored graph for the
job's dataset, with its label vocabulary so the legend survives a reconnect),
then a stream of `delta` frames as chunks land, a `vocabulary` frame whenever a
delta introduces new labels, and finally `done` at a terminal job status.

R14: `subscribe` is terminated only by the `close()` sentinel, and `close()`
reaches only the queues registered at close time — a client that connects AFTER
the job closed would therefore park forever. This route never relies on the
sentinel: it races the subscription against a bounded job-status poll so
completion ends the stream even with no sentinel. It subscribes (priming one
`__anext__`, which is what actually registers the queue) BEFORE reading the
snapshot, so a delta published while the snapshot is built is queued rather than
lost in the read→subscribe gap; the snapshot stays the FIRST frame sent.
"""
import asyncio
import json
import logging
from dataclasses import replace
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.api import graph_snapshot, graph_stream

router = APIRouter(tags=["graph"])

logger = logging.getLogger(__name__)

_TERMINAL = {"completed", "failed"}
_POLL_INTERVAL_S = 0.25
# Total grace window to flush deltas already queued when the terminal poll wins.
_DRAIN_GRACE_S = 0.1


async def _job_state(job_id: str) -> tuple[str, Optional[str]]:
    """(status, dataset_id) for a run — memory first, then the persisted run.

    Mirrors `api_server._ontology_from_run`: a job no longer in `RUNS` (server
    restarted, or evicted) is read back from its runtime JSON. Lazy import — the
    router is included before `RUNS` exists in `api_server`'s module body.
    """
    from src.api.api_server import RUNS, _RUNS_RUNTIME_DIR

    run = RUNS.get(job_id)
    if run is None:
        path = _RUNS_RUNTIME_DIR / f"{job_id}.json"
        if path.exists():
            try:
                run = json.loads(await asyncio.to_thread(path.read_text, "utf-8"))
            except (OSError, ValueError):
                run = None
    if run is None:
        return "failed", None
    result = run.get("result") or {}
    return run.get("status", "queued"), result.get("dataset_id")


async def _poll_until_terminal(job_id: str) -> None:
    """The sentinel-independent terminator: return once the job is done."""
    while True:
        status, _ = await _job_state(job_id)
        if status in _TERMINAL:
            return
        await asyncio.sleep(_POLL_INTERVAL_S)


async def _wait_disconnect(websocket: WebSocket) -> None:
    """Resolve when the client goes away, so an idle run is not left streaming."""
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
    except WebSocketDisconnect:
        return


async def _send_delta(websocket: WebSocket, delta) -> None:
    if delta.error:
        # A terminal chunk failure (Task 16): an error is not a delta, so it
        # replaces the delta frame rather than decorating one.
        await websocket.send_json({
            "type": "error",
            "chunk_id": delta.chunk_id,
            "message": delta.error,
        })
        return
    await websocket.send_json({
        "type": "delta",
        "nodes": delta.nodes,
        "edges": delta.edges,
        "chunk_id": delta.chunk_id,
        "progress": delta.progress,
    })
    if delta.new_labels:
        await websocket.send_json({
            "type": "vocabulary",
            "labels": delta.new_labels,
            "chunk_id": delta.chunk_id,
        })


def _dedupe(delta, seen_nodes, seen_edges):
    """Drop nodes/edges the snapshot already carried, so a delta published during
    the snapshot window is merged once rather than duplicated. Node identity is
    `id`; edge identity is `source|target|label` — the same keys the client
    upserts by. Error deltas carry no graph content, so they pass through
    unchanged. Returns the same object when nothing was dropped."""
    if delta.error or not (seen_nodes or seen_edges):
        return delta
    nodes = [n for n in delta.nodes if n.get("id") not in seen_nodes]
    edges = [
        e for e in delta.edges
        if (e.get("source"), e.get("target"), e.get("label")) not in seen_edges
    ]
    if len(nodes) == len(delta.nodes) and len(edges) == len(delta.edges):
        return delta
    return replace(delta, nodes=nodes, edges=edges)


async def _drain_queued(
    websocket: WebSocket,
    subscription,
    next_delta,
    seen_nodes=frozenset(),
    seen_edges=frozenset(),
):
    """Deliver deltas already queued when the terminator fires (bounded).

    The terminal poll can win the race a hair before the in-flight `__anext__`
    yields a chunk published on the same tick. Give it a short grace window and
    keep draining while items keep arriving, so that delta is not dropped before
    `done`. Reuses the SAME in-flight task throughout: a fresh one per iteration
    would cancel the generator mid-await and tear it down.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _DRAIN_GRACE_S
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            return next_delta
        done, _ = await asyncio.wait({next_delta}, timeout=remaining)
        if next_delta not in done:
            return next_delta  # nothing ready; leave the pending task for finally
        try:
            delta = next_delta.result()
        except StopAsyncIteration:
            return next_delta  # stream exhausted; nothing left to drain
        if delta is None:
            return next_delta
        await _send_delta(websocket, _dedupe(delta, seen_nodes, seen_edges))
        next_delta = asyncio.create_task(subscription.__anext__())


async def _stream(
    websocket: WebSocket,
    job_id: str,
    subscription,
    next_delta,
    seen_nodes,
    seen_edges,
) -> None:
    # `subscription` and its in-flight `next_delta` come from the route, which
    # registered the queue and primed the first `__anext__` BEFORE reading the
    # snapshot — so a delta published in that window is queued, not lost. One
    # `__anext__` at a time, kept across iterations: racing it with `wait_for`
    # would cancel the generator mid-await and tear it down, so the wait is on
    # the TASK, and the task survives a losing race.
    terminator = asyncio.create_task(_poll_until_terminal(job_id))
    watcher = asyncio.create_task(_wait_disconnect(websocket))
    try:
        while True:
            done, _ = await asyncio.wait(
                {next_delta, terminator, watcher}, return_when=asyncio.FIRST_COMPLETED
            )
            if watcher in done:
                return  # client gone
            if next_delta in done:
                try:
                    delta = next_delta.result()
                except StopAsyncIteration:
                    delta = None
                if delta is None:
                    break  # publisher closed the stream
                await _send_delta(websocket, _dedupe(delta, seen_nodes, seen_edges))
                next_delta = asyncio.create_task(subscription.__anext__())
                continue
            # terminator: the job reached completed/failed. Drain deltas already
            # queued so one published on the terminal tick is still delivered.
            next_delta = await _drain_queued(websocket, subscription, next_delta, seen_nodes, seen_edges)
            break
    finally:
        # An abandoned `async for` over the generator is only finalised at GC;
        # cancel the in-flight `__anext__` so its `finally` drops the queue
        # registration now. Closing the generator itself is the route's job.
        for task in (next_delta, terminator, watcher):
            task.cancel()
        await asyncio.gather(next_delta, terminator, watcher, return_exceptions=True)

    try:
        await websocket.send_json({"type": "done"})
    except (WebSocketDisconnect, RuntimeError):
        pass  # client disconnected between the terminal poll and this send


@router.websocket("/simulate/{job_id}/graph_stream")
async def stream_graph(websocket: WebSocket, job_id: str):
    await websocket.accept()

    # Resolve the dataset from the run, waiting out a queued job.
    status, dataset_id = await _job_state(job_id)
    while dataset_id is None and status not in _TERMINAL:
        await asyncio.sleep(_POLL_INTERVAL_S)
        status, dataset_id = await _job_state(job_id)

    if dataset_id is None:
        # Nothing was built for this job (unknown id, or a failure before the
        # dataset was known): there is no snapshot to send. Say done and leave.
        try:
            await websocket.send_json({"type": "done"})
        except WebSocketDisconnect:
            pass  # client hung up before the first frame
        return

    # Subscribe BEFORE reading the snapshot. Priming one `__anext__` is what
    # actually registers the queue (an async generator runs no body until first
    # iterated), so a delta published while the snapshot is built is queued —
    # not lost in the read→subscribe gap. The snapshot stays the FIRST frame
    # sent; anything queued is delivered after it, de-duplicated against the
    # snapshot by node id / edge key so no node is delivered twice.
    subscription = graph_stream.subscribe(job_id)
    next_delta = asyncio.create_task(subscription.__anext__())
    try:
        snapshot = await graph_snapshot.read_snapshot(dataset_id)
        await websocket.send_json({
            "type": "snapshot",
            "nodes": snapshot.nodes,
            "edges": snapshot.edges,
            "labels": snapshot.new_labels,
        })

        if status in _TERMINAL:
            # Already finished: the snapshot is the whole story. Say so and leave.
            await websocket.send_json({"type": "done"})
            return

        await _stream(
            websocket,
            job_id,
            subscription,
            next_delta,
            seen_nodes={n["id"] for n in snapshot.nodes},
            seen_edges={(e["source"], e["target"], e["label"]) for e in snapshot.edges},
        )
    except WebSocketDisconnect:
        # The client hung up mid-window — a reload, a StrictMode remount, or a
        # navigation closes the socket while the snapshot is being read, so a
        # send raises. That is a normal hang-up, not a fault: absorb it here so
        # it never escapes the ASGI app as an "Exception in ASGI application".
        # Covers the snapshot and terminal `done` sends, and any disconnect that
        # escapes `_stream`'s own sends.
        return
    except Exception as exc:
        # A data-retrieval failure after accept (e.g. Neo4j unreachable while
        # reading the snapshot) would otherwise escape the ASGI app — the HTTP
        # global handler does not cover WebSockets. Report it on the wire, where
        # the client already renders `error` frames, then close with `done`.
        logger.exception("graph_stream: snapshot read failed for dataset %s", dataset_id)
        try:
            await websocket.send_json({"type": "error", "message": f"snapshot read failed: {exc}"})
            await websocket.send_json({"type": "done"})
        except (WebSocketDisconnect, RuntimeError):
            pass  # client also gone; nothing left to send
        return
    finally:
        # Drop the registration and the in-flight `__anext__` on every exit path,
        # including a snapshot read that raised.
        next_delta.cancel()
        await asyncio.gather(next_delta, return_exceptions=True)
        await subscription.aclose()
