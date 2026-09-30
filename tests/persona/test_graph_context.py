"""Tests for GraphContext."""
import os
import pytest
import asyncio

import pytest_asyncio
from dotenv import load_dotenv

load_dotenv()

from src.persona.graph_context import GraphContext, EntityNode, EntityContext
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
