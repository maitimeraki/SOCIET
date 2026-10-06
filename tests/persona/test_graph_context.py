"""Tests for GraphContext."""
import os
import pytest
import asyncio
from unittest.mock import patch
from uuid import UUID

import pytest_asyncio
from dotenv import load_dotenv

load_dotenv()

from src.persona.graph_context import GraphContext, EntityNode, EntityContext
from src.persona.models_persona import ProvenanceLink
from src.graph.config_graph import GraphConfig


@pytest_asyncio.fixture
async def graph_ctx():
    """Create a GraphContext with Neo4j connection for testing."""
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    pwd = os.getenv("NEO4J_PASSWORD", "password")
    db = os.getenv("NEO4J_DATABASE", "neo4j")

    config = GraphConfig(
        neo4j_uri=uri,
        neo4j_username=user,
        neo4j_password=pwd,
        neo4j_database=db,
    )
    ctx = GraphContext(config)

    # Healthcheck; skip tests if Neo4j not available
    try:
        async with ctx._driver.session(database=db) as session:
            await session.run("RETURN 1")
    except Exception as e:
        await ctx.close()
        pytest.skip(f"Neo4j not available at {uri}: {e}")

    yield ctx

    await ctx.close()


@pytest_asyncio.fixture
async def seeded_node(graph_ctx):
    """Create a test node and yield its ID for cleanup."""
    node_id = "test_entity_graph_context"
    async with graph_ctx._driver.session(database=graph_ctx._db) as session:
        await session.run(
            """
            MERGE (n:Persona {name: $name})
            SET n.id = $id,
                n.summary = $summary,
                n.description = $desc,
                n.domain_tags = $tags,
                n._test = true
            """,
            name=node_id,
            id=node_id,
            summary="Test entity for graph context",
            desc="A test entity",
            tags=["test", "graph"],
        )
        # Create a neighbor
        await session.run(
            """
            MERGE (n:Persona {name: $name})
            MERGE (n)-[:RELATED]->(neighbor:Persona {name: $neighbor_name})
            """,
            name=node_id,
            neighbor_name="test_neighbor",
        )
        # Create provenance via MENTIONS
        await session.run(
            """
            MATCH (n:Persona {name: $name})
            CREATE (chunk:Chunk {doc_id: $doc_id, title: $title, breadcrumb: $breadcrumb, chunk_id: $chunk_id})
            CREATE (n)-[:MENTIONS]->(chunk)
            """,
            name=node_id,
            doc_id="doc:test_doc",
            title="Test Document",
            breadcrumb="Test > Section",
            chunk_id="12345678-1234-1234-1234-123456789abc",
        )

    yield node_id

    # Cleanup
    async with graph_ctx._driver.session(database=graph_ctx._db) as session:
        await session.run(
            "MATCH (n) WHERE n._test = true OR n.name = 'test_entity_graph_context' DETACH DELETE n"
        )
        await session.run(
            "MATCH (c:Chunk) WHERE c.doc_id = 'doc:test_doc' DELETE c"
        )


@pytest.mark.asyncio
async def test_find_relevant_entities_returns_list(graph_ctx):
    """Test that find_relevant_entities returns a list of EntityNode."""
    results = await graph_ctx.find_relevant_entities("test entity graph", limit=10)
    assert isinstance(results, list)
    for entity in results:
        assert isinstance(entity, EntityNode)
        assert entity.name is not None
        assert entity.relevance_score >= 0.0


@pytest.mark.asyncio
async def test_find_relevant_entities_respects_limit(graph_ctx):
    """Test that the limit parameter is respected."""
    results = await graph_ctx.find_relevant_entities("test", limit=3)
    assert len(results) <= 3


@pytest.mark.asyncio
async def test_get_entity_context_includes_neighbors(seeded_node, graph_ctx):
    """Test that get_entity_context returns neighbors."""
    context = await graph_ctx.get_entity_context(seeded_node)
    assert context is not None
    assert isinstance(context, EntityContext)
    assert context.entity is not None
    assert context.neighbors is not None
    assert isinstance(context.neighbors, list)


@pytest.mark.asyncio
async def test_get_entity_context_includes_provenance(seeded_node, graph_ctx):
    """Test that get_entity_context includes provenance."""
    context = await graph_ctx.get_entity_context(seeded_node)
    assert context is not None
    assert isinstance(context.provenance, list)


@pytest.mark.asyncio
async def test_get_entity_context_returns_none_for_nonexistent(graph_ctx):
    """Test that get_entity_context returns None for non-existent entity."""
    context = await graph_ctx.get_entity_context("nonexistent_entity_id_12345")
    assert context is None


@pytest.mark.asyncio
async def test_get_provenance_traces_to_source(seeded_node, graph_ctx):
    """Test that provenance traces back to source chunks."""
    provenance = await graph_ctx.get_provenance(seeded_node)
    assert isinstance(provenance, list)
    # Check that provenance entries have required fields
    for link in provenance:
        assert link.doc_id is not None
        assert link.title is not None


@pytest.mark.asyncio
async def test_get_provenance_empty_for_nonexistent(graph_ctx):
    """Test that get_provenance returns empty list for non-existent entity."""
    provenance = await graph_ctx.get_provenance("nonexistent_entity_id_12345")
    assert isinstance(provenance, list)
    assert len(provenance) == 0


@pytest.mark.asyncio
async def test_entity_node_model_validation(graph_ctx):
    """Test that EntityNode model validation works correctly."""
    node = EntityNode(
        id="test_id",
        name="Test Entity",
        label="Persona",
        properties={"key": "value"},
        relevance_score=0.95,
        summary="Test summary",
        domain_tags=["test", "unit"],
    )
    assert node.id == "test_id"
    assert node.name == "Test Entity"
    assert node.relevance_score == 0.95
    assert "test" in node.domain_tags


@pytest.mark.asyncio
async def test_entity_context_dataclass(graph_ctx):
    """Test that EntityContext dataclass holds all components."""
    # Create minimal context for testing the dataclass
    entity = EntityNode(
        id="test",
        name="Test",
        label="Test",
    )
    context = EntityContext(
        entity=entity,
        neighbors=[],
        provenance=[],
    )
    assert context.entity == entity
    assert context.neighbors == []
    assert context.provenance == []


@pytest.mark.asyncio
async def test_async_context_manager(graph_ctx):
    """Test that GraphContext works as an async context manager."""
    async with GraphContext(graph_ctx.config) as ctx:
        results = await ctx.find_relevant_entities("test", limit=5)
        assert isinstance(results, list)


# ---- Batched provenance: ONE query serves the whole roster (Task 9) ----
#
# These run against a query-counting fake driver (no live Neo4j), so the
# query count is deterministic and independent of the seeded graph.

class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    async def data(self):
        return list(self._rows)

    async def single(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, driver):
        self._driver = driver

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def run(self, cypher, **params):
        self._driver.queries.append((str(cypher), params))
        return _FakeResult(self._driver.responder(str(cypher), params))


class _RecordingDriver:
    """Counts every executed query; answers each with `responder`'s rows."""

    def __init__(self, responder):
        self.responder = responder
        self.queries = []

    def session(self, database=None):
        return _FakeSession(self)


def _batch_ctx(responder):
    ctx = GraphContext.__new__(GraphContext)
    ctx._db = "neo4j"
    ctx._driver = _RecordingDriver(responder)
    return ctx, ctx._driver


def _chunk_row(node_id, node_name, doc_id, chunk_id, title="T", breadcrumb="b"):
    return {
        "node_id": node_id, "node_name": node_name, "doc_id": doc_id,
        "title": title, "breadcrumb": breadcrumb, "chunk_id": chunk_id,
    }


@pytest.mark.asyncio
async def test_get_provenance_batch_serves_the_whole_roster_with_one_query():
    """N entities → ONE executed query; a mixed result maps per entity."""
    rows = [
        _chunk_row("e1", "Alpha", "doc:1", "11111111-1111-1111-1111-111111111111"),
        _chunk_row("e1", "Alpha", "doc:2", "22222222-2222-2222-2222-222222222222"),
        _chunk_row("e2", "Beta", "doc:1", "33333333-3333-3333-3333-333333333333"),
    ]
    ctx, driver = _batch_ctx(lambda cypher, params: rows)

    result = await ctx.get_provenance_batch(["e1", "e2", "e3"])

    assert len(driver.queries) == 1  # the whole roster, one query
    cypher, params = driver.queries[0]
    assert "MENTIONS" in cypher and "$entity_ids" in cypher
    assert params["entity_ids"] == ["e1", "e2", "e3"]
    assert set(result) == {"e1", "e2", "e3"}  # keyed by the roster's keys
    assert [link.doc_id for link in result["e1"]] == ["doc:1", "doc:2"]  # order kept
    assert [link.doc_id for link in result["e2"]] == ["doc:1"]
    assert result["e3"] == []  # no chunks → empty, never missing
    link = result["e1"][0]
    assert isinstance(link, ProvenanceLink)
    assert link.chunk_id == UUID("11111111-1111-1111-1111-111111111111")


@pytest.mark.asyncio
async def test_get_provenance_batch_attributes_rows_by_id_and_name():
    """A row reaches every requested key that its id or name matches."""
    rows = [
        _chunk_row("not-requested", "Alpha", "doc:1", "44444444-4444-4444-4444-444444444444"),
        _chunk_row("e2", "Alpha", "doc:2", "55555555-5555-5555-5555-555555555555"),
    ]
    ctx, _ = _batch_ctx(lambda cypher, params: rows)

    result = await ctx.get_provenance_batch(["Alpha", "e2"])

    # Matches the two single fetches exactly: get_provenance("Alpha") hits both
    # rows (one by name, one by id-or-name), get_provenance("e2") hits the second.
    assert [link.doc_id for link in result["Alpha"]] == ["doc:1", "doc:2"]
    assert [link.doc_id for link in result["e2"]] == ["doc:2"]


@pytest.mark.asyncio
async def test_get_provenance_batch_empty_roster_runs_no_query():
    ctx, driver = _batch_ctx(lambda cypher, params: pytest.fail("query executed for an empty roster"))

    assert await ctx.get_provenance_batch([]) == {}
    assert driver.queries == []


@pytest.mark.asyncio
async def test_get_provenance_batch_serves_a_live_roster(seeded_node, graph_ctx):
    """The batch Cypher itself executes against live Neo4j with single-fetch parity."""
    result = await graph_ctx.get_provenance_batch([seeded_node, "nonexistent_entity_id_12345"])

    assert result["nonexistent_entity_id_12345"] == []
    docs = [link.doc_id for link in result[seeded_node]]
    assert "doc:test_doc" in docs
    for link in result[seeded_node]:
        assert isinstance(link, ProvenanceLink)
        assert link.title is not None

    single = await graph_ctx.get_provenance(seeded_node)
    assert [link.doc_id for link in single] == docs  # same result, same order


# ---- Bounded embed calls: env-backed base URL + timeout (Task 11) ----

def test_embed_model_is_bounded_and_env_addressed(monkeypatch):
    """OllamaEmbedding gets LLMConfig's Ollama base URL plus a request timeout."""
    from src.llm.config_llm import LLMConfig

    monkeypatch.setattr(LLMConfig, "ollama_base_url", "http://sentinel-ollama:1234")

    with patch('src.persona.graph_context.AsyncGraphDatabase'), \
         patch('src.persona.graph_context.OllamaEmbedding') as mock_embed:
        GraphContext(GraphConfig())

    kwargs = mock_embed.call_args.kwargs
    assert kwargs["base_url"] == "http://sentinel-ollama:1234"
    assert kwargs["client_kwargs"]["timeout"] == 60
