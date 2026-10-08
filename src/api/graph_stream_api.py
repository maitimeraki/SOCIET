"""Task 9 — the live-graph WebSocket route.

One channel carries the whole live graph so the UI never polls REST for graph
state. On connect a client gets a `snapshot` (the full stored graph for the
job's dataset, with its label vocabulary so the legend survives a reconnect),
then a stream of `delta` frames as chunks land, a `vocabulary` frame whenever a
delta introduces new labels, and finally `done` at a terminal job status.

R14: `subscribe` is terminated only by the `close()` sentinel, and `close()`
reaches only the queues registered at close time — a client that connects AFTER
the job closed would therefore park forever. This route never relies on the
sentinel: it resolves the job and sends the snapshot BEFORE subscribing, and it
races the subscription against a bounded job-status poll so completion ends the
stream even with no sentinel.
"""
import asyncio
import json
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.api import graph_snapshot, graph_stream

router = APIRouter(tags=["graph"])

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


async def _drain_queued(websocket: WebSocket, subscription, next_delta):
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
        await _send_delta(websocket, delta)
        next_delta = asyncio.create_task(subscription.__anext__())


async def _stream(websocket: WebSocket, job_id: str) -> None:
    subscription = graph_stream.subscribe(job_id)
    # One in-flight `__anext__` at a time, kept across iterations: racing it with
    # `wait_for` would cancel the generator mid-await and tear it down, so the
    # wait is on the TASK, and the task survives a losing race.
    next_delta = asyncio.create_task(subscription.__anext__())
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
                await _send_delta(websocket, delta)
                next_delta = asyncio.create_task(subscription.__anext__())
                continue
            # terminator: the job reached completed/failed. Drain deltas already
            # queued so one published on the terminal tick is still delivered.
            next_delta = await _drain_queued(websocket, subscription, next_delta)
            break
    finally:
        # An abandoned `async for` over the generator is only finalised at GC;
        # cancel the in-flight `__anext__` and close the generator explicitly so
        # its `finally` drops the queue registration now.
        for task in (next_delta, terminator, watcher):
            task.cancel()
        await asyncio.gather(next_delta, terminator, watcher, return_exceptions=True)
        await subscription.aclose()

    try:
        await websocket.send_json({"type": "done"})
    except (WebSocketDisconnect, RuntimeError):
        pass  # client disconnected between the terminal poll and this send


@router.websocket("/simulate/{job_id}/graph_stream")
async def stream_graph(websocket: WebSocket, job_id: str):
    await websocket.accept()

    # Resolve the dataset from the run, waiting out a queued job, then send the
    # snapshot BEFORE subscribing: a client joining after the build closed still
    # gets the full state (R14).
    status, dataset_id = await _job_state(job_id)
    while dataset_id is None and status not in _TERMINAL:
        await asyncio.sleep(_POLL_INTERVAL_S)
        status, dataset_id = await _job_state(job_id)

    if dataset_id is not None:
        snapshot = await graph_snapshot.read_snapshot(dataset_id)
        await websocket.send_json({
            "type": "snapshot",
            "nodes": snapshot.nodes,
            "edges": snapshot.edges,
            "labels": snapshot.new_labels,
        })

    if status in _TERMINAL:
        # Already finished: the snapshot is the whole story. Say so and leave —
        # subscribing here would hang on a sentinel that will never arrive.
        await websocket.send_json({"type": "done"})
        return

    await _stream(websocket, job_id)
