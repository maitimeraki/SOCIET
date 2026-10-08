"""In-process pub/sub for live graph streaming.

Task 7 publishes a GraphDelta the moment each chunk's extraction finishes;
Task 9 subscribes from a WebSocket route and forwards the frames.

Single event loop, so a set of asyncio.Queues per job under a plain lock is
enough. Re-subscribing after close() starts a fresh stream: close() clears the
job's entries, so a reconnect simply sees nothing published before it
re-subscribed.
"""
import asyncio
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class GraphDelta:
    nodes: list[dict] = field(default_factory=list)   # each {id, label, type}
    edges: list[dict] = field(default_factory=list)   # each {source, target, label}
    new_labels: list[str] = field(default_factory=list)
    chunk_id: str = ""
    progress: float = 0.0


_CLOSED = object()  # sentinel: distinct from any GraphDelta payload

_registry: dict[str, set[asyncio.Queue]] = {}
_lock = asyncio.Lock()


def publish(job_id: str, delta: GraphDelta) -> None:
    for queue in _registry.get(job_id, ()):
        queue.put_nowait(delta)


async def subscribe(job_id: str) -> AsyncIterator[GraphDelta]:
    queue: asyncio.Queue = asyncio.Queue()
    async with _lock:
        _registry.setdefault(job_id, set()).add(queue)

    try:
        while True:
            item = await queue.get()
            if item is _CLOSED:
                return
            yield item
    finally:
        async with _lock:
            queues = _registry.get(job_id)
            if queues is not None:
                queues.discard(queue)
                if not queues:
                    _registry.pop(job_id, None)


def close(job_id: str) -> None:
    for queue in _registry.pop(job_id, ()):
        queue.put_nowait(_CLOSED)
