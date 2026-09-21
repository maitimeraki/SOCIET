"""Tests for ProvenanceTracker."""
import os
import pytest
import asyncio
from uuid import uuid4

import pytest_asyncio
from dotenv import load_dotenv

load_dotenv()

from src.persona.provenance import ProvenanceTracker, SourceChunk, SourceDocument, ProvenanceChain
from src.simulation.agent_node import AgentNode, Stance
from src.graph.config_graph import GraphConfig


@pytest_asyncio.fixture
async def tracker():
    """Create a ProvenanceTracker with Neo4j connection for testing."""
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
    tracker = ProvenanceTracker(config)

    # Healthcheck; skip tests if Neo4j not available
    try:
        async with tracker._driver.session(database=db) as session:
            await session.run("RETURN 1")
    except Exception as e:
        await tracker.close()
        pytest.skip(f"Neo4j not available at {uri}: {e}")

    yield tracker
    await tracker.close()


@pytest_asyncio.fixture
async def test_agent(tracker):
    """Create a test agent and cleanup after test."""
    from src.persona.agent_repository import AgentRepository
    repo = AgentRepository(tracker._config)
    agent = AgentNode(
        name=f"Test Agent {uuid4().hex[:8]}",
        archetype="TEST",
        stance=Stance.NEUTRAL,
        domain_tags=["test"],
    )
    created = await repo.create_agent(agent)
    agent_id = str(created.id)
    await repo.close()

    yield agent_id

    # Cleanup: delete agent and its relationships
    try:
        async with tracker._driver.session(database=tracker._db) as session:
            await session.run(
                "MATCH (a:Agent {id: $id}) DETACH DELETE a",
                id=agent_id
            )
    except Exception:
        pass


@pytest_asyncio.fixture
async def test_entity(tracker):
    """Create a test entity and cleanup after test."""
    from src.graph.graph_build import GraphBuilder
    builder = GraphBuilder(tracker._config)
    entity = await builder.create_entity(
        name=f"Test Entity {uuid4().hex[:8]}",
        entity_type="CONCEPT",
        properties={"description": "Test entity for provenance tracking"},
    )
    entity_id = str(entity)
    await builder.close()

    yield entity_id

    # Cleanup
    try:
        async with tracker._driver.session(database=tracker._db) as session:
            await session.run(
                "MATCH (e:Entity {id: $id}) DETACH DELETE e",
                id=entity_id
            )
    except Exception:
        pass


@pytest.mark.asyncio
async def test_cite_entity_creates_relationship(tracker, test_agent, test_entity):
    """Test that cite_entity creates a CITES relationship."""
    response_id = f"response-{uuid4().hex[:8]}"

    await tracker.cite_entity(test_agent, test_entity, response_id)

    # Verify the relationship exists
    cited = await tracker.get_cited_entities(test_agent, response_id)
    assert test_entity in cited


@pytest.mark.asyncio
async def test_cite_entity_multiple_entities(tracker, test_agent):
    """Test citing multiple entities in one response."""
    # Create multiple test entities
    from src.graph.graph_build import GraphBuilder
    builder = GraphBuilder(tracker._config)

    entities = []
    for i in range(3):
        entity = await builder.create_entity(
            name=f"Multi Entity {i} {uuid4().hex[:4]}",
            entity_type="CONCEPT",
            properties={"description": f"Entity {i}"},
        )
        entities.append(str(entity))

    await builder.close()

    response_id = f"response-{uuid4().hex[:8]}"

    # Cite all entities
    for entity_id in entities:
        await tracker.cite_entity(test_agent, entity_id, response_id)

    # Verify all are cited
    cited = await tracker.get_cited_entities(test_agent, response_id)
    for entity_id in entities:
        assert entity_id in cited

    # Cleanup entities
    for entity_id in entities:
        try:
            async with tracker._driver.session(database=tracker._db) as session:
                await session.run(
                    "MATCH (e:Entity {id: $id}) DETACH DELETE e",
                    id=entity_id
                )
        except Exception:
            pass


@pytest.mark.asyncio
async def test_trace_response_returns_chain(tracker, test_agent, test_entity):
    """Test that trace_response returns a ProvenanceChain."""
    response_id = f"response-{uuid4().hex[:8]}"

    # Cite an entity
    await tracker.cite_entity(test_agent, test_entity, response_id)

    # Trace the response
    chain = await tracker.trace_response(test_agent, response_id)

    assert isinstance(chain, ProvenanceChain)
    assert chain.response_id == response_id
    assert chain.agent_id == test_agent
    assert test_entity in chain.cited_entities


@pytest.mark.asyncio
async def test_trace_response_empty_for_uncited(tracker, test_agent):
    """Test trace_response for response with no citations."""
    response_id = f"response-{uuid4().hex[:8]}"

    chain = await tracker.trace_response(test_agent, response_id)

    assert isinstance(chain, ProvenanceChain)
    assert chain.response_id == response_id
    assert chain.agent_id == test_agent
    assert len(chain.cited_entities) == 0
    assert len(chain.source_chunks) == 0


@pytest.mark.asyncio
async def test_trace_response_confidence_calculation(tracker, test_agent, test_entity):
    """Test that confidence is calculated based on citations."""
    response_id = f"response-{uuid4().hex[:8]}"

    # No citations should give 0 confidence
    chain = await tracker.trace_response(test_agent, response_id)
    assert chain.confidence == 0.0

    # Add citations and check confidence increases
    await tracker.cite_entity(test_agent, test_entity, response_id)
    chain = await tracker.trace_response(test_agent, response_id)
    # 1 entity * 0.3 = 0.3
    assert chain.confidence == 0.3


@pytest.mark.asyncio
async def test_get_source_documents_empty_for_no_chunks(tracker, test_agent, test_entity):
    """Test get_source_documents returns empty list when no chunks exist."""
    response_id = f"response-{uuid4().hex[:8]}"

    await tracker.cite_entity(test_agent, test_entity, response_id)

    documents = await tracker.get_source_documents(test_agent, response_id)

    assert isinstance(documents, list)
    assert len(documents) == 0


@pytest.mark.asyncio
async def test_get_source_documents_returns_list(tracker, test_agent):
    """Test get_source_documents returns a list of SourceDocument."""
    response_id = f"response-{uuid4().hex[:8]}"

    documents = await tracker.get_source_documents(test_agent, response_id)

    assert isinstance(documents, list)
    # All items should be SourceDocument
    for doc in documents:
        assert isinstance(doc, SourceDocument)
        assert hasattr(doc, 'document_id')
        assert hasattr(doc, 'title')
        assert hasattr(doc, 'path')


@pytest.mark.asyncio
async def test_get_cited_entities_returns_list(tracker, test_agent, test_entity):
    """Test get_cited_entities returns list of entity IDs."""
    response_id = f"response-{uuid4().hex[:8]}"

    await tracker.cite_entity(test_agent, test_entity, response_id)

    cited = await tracker.get_cited_entities(test_agent, response_id)

    assert isinstance(cited, list)
    assert len(cited) >= 1
    assert test_entity in cited


@pytest.mark.asyncio
async def test_get_cited_entities_empty_for_unknown_response(tracker, test_agent):
    """Test get_cited_entities returns empty list for unknown response."""
    response_id = f"unknown-response-{uuid4().hex[:8]}"

    cited = await tracker.get_cited_entities(test_agent, response_id)

    assert isinstance(cited, list)
    assert len(cited) == 0


@pytest.mark.asyncio
async def test_source_chunk_dataclass():
    """Test SourceChunk dataclass creation."""
    chunk = SourceChunk(
        chunk_id="chunk-123",
        content="This is test content",
        source_document="doc-456",
    )

    assert chunk.chunk_id == "chunk-123"
    assert chunk.content == "This is test content"
    assert chunk.source_document == "doc-456"


@pytest.mark.asyncio
async def test_source_document_dataclass():
    """Test SourceDocument dataclass creation."""
    doc = SourceDocument(
        document_id="doc-789",
        title="Test Document",
        path="/path/to/doc",
    )

    assert doc.document_id == "doc-789"
    assert doc.title == "Test Document"
    assert doc.path == "/path/to/doc"


@pytest.mark.asyncio
async def test_provenance_chain_dataclass():
    """Test ProvenanceChain dataclass creation."""
    chain = ProvenanceChain(
        response_id="resp-001",
        agent_id="agent-001",
        cited_entities=["entity-1", "entity-2"],
        source_chunks=[
            SourceChunk("c1", "content1", "doc1"),
            SourceChunk("c2", "content2", "doc2"),
        ],
        confidence=0.8,
    )

    assert chain.response_id == "resp-001"
    assert chain.agent_id == "agent-001"
    assert len(chain.cited_entities) == 2
    assert len(chain.source_chunks) == 2
    assert chain.confidence == 0.8


@pytest.mark.asyncio
async def test_trace_response_across_multiple_responses(tracker, test_agent, test_entity):
    """Test that citations are correctly scoped to specific responses."""
    response1 = f"response-1-{uuid4().hex[:8]}"
    response2 = f"response-2-{uuid4().hex[:8]}"

    # Cite entity in response1 only
    await tracker.cite_entity(test_agent, test_entity, response1)

    # Check response1 has citation
    chain1 = await tracker.trace_response(test_agent, response1)
    assert test_entity in chain1.cited_entities

    # Check response2 has no citation
    chain2 = await tracker.trace_response(test_agent, response2)
    assert test_entity not in chain2.cited_entities
    assert len(chain2.cited_entities) == 0


@pytest.mark.asyncio
async def test_provenance_chain_source_chunks_list(tracker, test_agent, test_entity):
    """Test that ProvenanceChain correctly holds source_chunks list."""
    response_id = f"response-{uuid4().hex[:8]}"

    chain = await tracker.trace_response(test_agent, response_id)

    assert isinstance(chain.source_chunks, list)
    # Can be empty or populated based on graph state
    for chunk in chain.source_chunks:
        assert isinstance(chunk, SourceChunk)
