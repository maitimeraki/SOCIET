"""Every graph read must carry the dataset predicate and bind $dataset_id (audit C1)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.graph.scope import chunk_in_dataset, entity_in_dataset
from src.persona.graph_context import GraphContext


class _Recorder:
    """A fake Neo4j driver that records every (query, params) pair."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        result = MagicMock()
        result.data = AsyncMock(return_value=[])
        result.single = AsyncMock(return_value=None)
        session = MagicMock()

        async def run(query, **params):
            self.calls.append((str(query), params))
            return result

        session.run = run
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        self.driver = MagicMock()
        self.driver.session = MagicMock(return_value=session)


def _context(recorder: _Recorder) -> GraphContext:
    ctx = GraphContext.__new__(GraphContext)
    ctx._driver = recorder.driver
    ctx._db = "neo4j"
    ctx._get_embedding = AsyncMock(return_value=[0.1, 0.2])
    return ctx


READS = {
    "find_relevant_entities": lambda ctx, **kw: ctx.find_relevant_entities("q", **kw),
    "find_connected_nodes": lambda ctx, **kw: ctx.find_connected_nodes(["a"], **kw),
    "find_connected_nodes_by_seed": lambda ctx, **kw: ctx.find_connected_nodes_by_seed(
        ["a"], **kw
    ),
    "_get_entity_by_id": lambda ctx, **kw: ctx._get_entity_by_id("a", **kw),
    "_get_neighbors": lambda ctx, **kw: ctx._get_neighbors("a", **kw),
    "get_provenance": lambda ctx, **kw: ctx.get_provenance("a", **kw),
    "get_provenance_batch": lambda ctx, **kw: ctx.get_provenance_batch(["a"], **kw),
    "get_entity_context": lambda ctx, **kw: ctx.get_entity_context("a", **kw),
}


def test_predicates_reference_the_bound_parameter():
    assert "$dataset_id" in entity_in_dataset("n")
    assert "DERIVED_FROM" in entity_in_dataset("n")
    assert chunk_in_dataset("c") == "c.dataset_id = $dataset_id"


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(READS))
async def test_graph_context_reads_bind_the_dataset(name):
    recorder = _Recorder()
    await READS[name](_context(recorder), dataset_id="ds-A")
    assert recorder.calls, "the read issued no query"
    for query, params in recorder.calls:
        assert "dataset_id" in query
        assert params.get("dataset_id") == "ds-A"


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(READS))
async def test_dataset_id_is_required(name):
    with pytest.raises(TypeError):
        await READS[name](_context(_Recorder()))


@pytest.mark.asyncio
async def test_provenance_or_is_parenthesised_so_the_chunk_guard_binds_both_keys():
    recorder = _Recorder()
    await _context(recorder).get_provenance("a", dataset_id="ds-A")
    query, _ = recorder.calls[0]
    assert "(n.id = $entity_id OR n.name = $entity_id)" in query
