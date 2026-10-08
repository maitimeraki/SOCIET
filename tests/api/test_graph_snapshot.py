"""Task 8 — dataset-scoped graph snapshot for reconnect.

A browser that reconnects mid-build has missed every prior GraphDelta, so
Task 9's WebSocket route hands it this snapshot as the opening frame: every
stored entity and relation for the dataset, plus the dataset's full label set
so the legend survives the refresh. No live Neo4j — `structured_query` is
stubbed on a recorder store, as in tests/graph/test_document_model.py.
"""
import pytest

import src.api.graph_snapshot as graph_snapshot
from src.api.graph_stream import GraphDelta


class _FakeStore:
    """structured_query seam: records (query, params), returns canned rows.

    Branches on the edges query's `AS source` projection so one fake serves both
    reads. The rows are the shape llama-index's driver returns: `d.data()`.
    """

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def structured_query(self, query, param_map=None):
        self.calls.append((query, param_map or {}))
        if " AS source" in query:
            return [{"source": "Person:Alice", "target": "Org:Acme", "label": "WORKS_AT"}]
        return [
            {"id": "Person:Alice", "label": "Alice", "type": "Person"},
            {"id": "Org:Acme", "label": "Acme", "type": "Organization"},
        ]


@pytest.fixture
def store(monkeypatch):
    fake = _FakeStore()
    monkeypatch.setattr(graph_snapshot, "Neo4jPropertyGraphStore", lambda **_: fake)
    monkeypatch.setattr(graph_snapshot, "_STORE", None)
    return fake


@pytest.mark.asyncio
async def test_snapshot_returns_nodes_edges_and_the_full_label_set(store):
    delta = await graph_snapshot.read_snapshot("ds-1")

    assert isinstance(delta, GraphDelta)
    assert delta.nodes == [
        {"id": "Person:Alice", "label": "Alice", "type": "Person"},
        {"id": "Org:Acme", "label": "Acme", "type": "Organization"},
    ]
    assert delta.edges == [
        {"source": "Person:Alice", "target": "Org:Acme", "label": "WORKS_AT"}
    ]
    # EVERY distinct entity label — not just the first node's — so the legend rebuilds
    assert set(delta.new_labels) == {"Person", "Organization"}


@pytest.mark.asyncio
async def test_both_reads_are_scoped_by_dataset_id(store):
    await graph_snapshot.read_snapshot("ds-42")

    assert len(store.calls) == 2
    for query, params in store.calls:
        assert params == {"dataset_id": "ds-42"}
        # scoped by the Document traversal, the one mechanism graph_build writes
        assert "DERIVED_FROM" in query
        assert "Document {dataset_id: $dataset_id}" in query


@pytest.mark.asyncio
async def test_chunk_id_and_progress_use_the_dataclass_defaults(store):
    delta = await graph_snapshot.read_snapshot("ds-1")

    assert delta.chunk_id == ""
    assert delta.progress == 0.0


@pytest.mark.asyncio
async def test_store_is_built_off_the_event_loop(monkeypatch):
    """`_get_store` issues blocking Neo4j schema round-trips on construction
    (refresh_schema defaults on), so building it must NOT happen on the event
    loop — otherwise the first read stalls every other FastAPI request."""
    import threading

    built_on: dict = {}

    def _factory(**kwargs):
        built_on["thread"] = threading.current_thread()
        return _FakeStore()

    monkeypatch.setattr(graph_snapshot, "Neo4jPropertyGraphStore", _factory)
    monkeypatch.setattr(graph_snapshot, "_STORE", None)

    await graph_snapshot.read_snapshot("ds-1")

    assert "thread" in built_on, "the store factory was never invoked"
    assert built_on["thread"] is not threading.main_thread()
