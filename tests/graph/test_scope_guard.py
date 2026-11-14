"""Every graph read must carry the dataset predicate and bind $dataset_id (audit C1)."""
from unittest.mock import AsyncMock

import pytest

from src.graph.scope import chunk_in_dataset, entity_in_dataset
from src.persona.graph_context import GraphContext


def _context(recorder) -> GraphContext:
    ctx = GraphContext.__new__(GraphContext)
    ctx._driver = recorder.driver
    ctx._db = "neo4j"
    ctx._get_embedding = AsyncMock(return_value=[0.1, 0.2])
    return ctx


# Each read, and the predicates its Cypher must contain: one per graph end the
# read touches. The walks and the neighbour read must scope BOTH ends.
READS = {
    "find_relevant_entities": (
        lambda ctx, **kw: ctx.find_relevant_entities("q", **kw),
        [entity_in_dataset("node")],
    ),
    "find_connected_nodes": (
        lambda ctx, **kw: ctx.find_connected_nodes(["a"], **kw),
        [entity_in_dataset("seed"), entity_in_dataset("n")],
    ),
    "find_connected_nodes_by_seed": (
        lambda ctx, **kw: ctx.find_connected_nodes_by_seed(["a"], **kw),
        [entity_in_dataset("seed"), entity_in_dataset("n")],
    ),
    "_get_entity_by_id": (
        lambda ctx, **kw: ctx._get_entity_by_id("a", **kw),
        [entity_in_dataset("n")],
    ),
    "_get_neighbors": (
        lambda ctx, **kw: ctx._get_neighbors("a", **kw),
        [
            entity_in_dataset("n"),
            entity_in_dataset("m"),
            "(m:Chunk AND " + chunk_in_dataset("m") + ")",
        ],
    ),
    "get_provenance": (
        lambda ctx, **kw: ctx.get_provenance("a", **kw),
        [entity_in_dataset("n"), chunk_in_dataset("chunk")],
    ),
    "get_provenance_batch": (
        lambda ctx, **kw: ctx.get_provenance_batch(["a"], **kw),
        [entity_in_dataset("n"), chunk_in_dataset("chunk")],
    ),
    "get_entity_context": (
        lambda ctx, **kw: ctx.get_entity_context("a", **kw),
        [entity_in_dataset("n"), entity_in_dataset("m"), chunk_in_dataset("chunk")],
    ),
}


def test_predicates_reference_the_bound_parameter():
    assert "$dataset_id" in entity_in_dataset("n")
    assert "DERIVED_FROM" in entity_in_dataset("n")
    assert chunk_in_dataset("c") == "c.dataset_id = $dataset_id"


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(READS))
async def test_graph_context_reads_bind_the_dataset(name, recorder):
    read, required = READS[name]
    await read(_context(recorder), dataset_id="ds-A")
    assert recorder.calls, "the read issued no query"
    for query, params in recorder.calls:
        assert "$dataset_id" in query
        assert params.get("dataset_id") == "ds-A"


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(READS))
async def test_graph_context_reads_scope_every_graph_end(name, recorder):
    read, required = READS[name]
    await read(_context(recorder), dataset_id="ds-A")
    for predicate in required:
        assert any(predicate in query for query, _ in recorder.calls), predicate


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(READS))
async def test_dataset_id_is_required(name, recorder):
    read, _ = READS[name]
    with pytest.raises(TypeError):
        await read(_context(recorder))


@pytest.mark.asyncio
async def test_provenance_or_is_parenthesised_so_the_chunk_guard_binds_both_keys(recorder):
    await _context(recorder).get_provenance("a", dataset_id="ds-A")
    query, _ = recorder.calls[0]
    assert "(n.id = $entity_id OR n.name = $entity_id)" in query
