"""Tests for the in-process graph delta pub/sub (Task 6).

Backs the live graph streaming path: Task 7 publishes a GraphDelta per chunk,
Task 9 forwards them over a WebSocket via subscribe().
"""
import asyncio

import pytest

from src.api.graph_stream import GraphDelta, close, publish, subscribe


def _delta(chunk_id: str, progress: float) -> GraphDelta:
    return GraphDelta(
        nodes=[{"id": f"n-{chunk_id}", "label": "PERSON", "type": "entity"}],
        edges=[{"source": "a", "target": "b", "label": "RELATED_TO"}],
        new_labels=["PERSON"],
        chunk_id=chunk_id,
        progress=progress,
    )


@pytest.mark.asyncio
async def test_subscriber_receives_deltas_in_order_then_stops():
    job_id = "job-order"
    first, second = _delta("c0", 0.5), _delta("c1", 1.0)

    received = []

    async def consume():
        async for delta in subscribe(job_id):
            received.append(delta)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0)  # let the subscriber register before publishing

    publish(job_id, first)
    publish(job_id, second)
    close(job_id)

    await asyncio.wait_for(task, timeout=1.0)

    assert received == [first, second]


@pytest.mark.asyncio
async def test_close_terminates_every_active_subscriber():
    job_id = "job-fanout"
    received = []

    async def consume():
        async for delta in subscribe(job_id):
            received.append(delta)

    tasks = [asyncio.create_task(consume()) for _ in range(3)]
    await asyncio.sleep(0)

    publish(job_id, _delta("c0", 0.2))
    close(job_id)

    await asyncio.wait_for(asyncio.gather(*tasks), timeout=1.0)

    assert len(received) == 3  # one delta fanned out to each subscriber


@pytest.mark.asyncio
async def test_close_after_subscription_before_publish_stops_iterator():
    job_id = "job-early-close"
    seen = []

    async def consume():
        async for delta in subscribe(job_id):
            seen.append(delta)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0)

    close(job_id)

    await asyncio.wait_for(task, timeout=1.0)

    assert seen == []


def test_publish_with_no_subscriber_is_a_noop():
    # Chunks can finish before the WebSocket client connects.
    publish("job-nobody", _delta("c0", 0.1))


def test_close_unknown_job_is_a_noop():
    close("job-never-existed")
