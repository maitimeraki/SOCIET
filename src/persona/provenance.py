"""
ProvenanceTracker: Track provenance of agent responses to source entities and documents.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from neo4j import AsyncGraphDatabase
from typing import cast, LiteralString

from src.graph.config_graph import GraphConfig
from src.logging.setup_logging import setup_logging

logger = setup_logging()


@dataclass
class SourceChunk:
    """Represents a chunk of content from a source document."""
    chunk_id: str
    content: str
    source_document: str


@dataclass
class SourceDocument:
    """Represents a source document that contributed to a response."""
    document_id: str
    title: str
    path: str


@dataclass
class ProvenanceChain:
    """Represents the provenance chain of a response."""
    response_id: str
    agent_id: str
    cited_entities: List[str]
    source_chunks: List[SourceChunk]
    confidence: float


class ProvenanceTracker:
    """Track provenance of agent responses to source entities and documents."""

    def __init__(self, config: GraphConfig | None = None):
        self._config = config or GraphConfig()
        self._driver = AsyncGraphDatabase.driver(
            self._config.neo4j_uri,
            auth=(self._config.neo4j_username, self._config.neo4j_password),
        )
        self._db = self._config.neo4j_database

    async def close(self) -> None:
        """Close the Neo4j driver."""
        await self._driver.close()

    async def cite_entity(
        self, agent_id: str, entity_id: str, response_id: str
    ) -> None:
        """Record that an agent cited an entity in a response.

        Creates a CITES relationship between the agent and entity node,
        with the response_id as a property for traceability.
        """
        query_cypher = """
        MATCH (a:Agent {id: $agent_id})
        MATCH (e:Entity {id: $entity_id})
        CREATE (a)-[r:CITES {
            response_id: $response_id,
            timestamp: datetime(),
            cited_at: datetime()
        }]->(e)
        RETURN id(r) AS rel_id
        """

        params = {
            "agent_id": agent_id,
            "entity_id": entity_id,
            "response_id": response_id,
        }

        async with self._driver.session(database=self._db) as session:
            await session.run(cast(LiteralString, query_cypher), **params)
            logger.debug(f"Agent {agent_id} cited entity {entity_id} for response {response_id}")

    async def trace_response(
        self, agent_id: str, response_id: str
    ) -> ProvenanceChain:
        """Trace a response back to source entities.

        Follows the CITES relationships from the agent to find all entities
        cited in this response, and traces back to source chunks.
        """
        # First get cited entities
        entities_query = """
        MATCH (a:Agent {id: $agent_id})-[r:CITES {response_id: $response_id}]->(e:Entity)
        RETURN e.id AS entity_id,
               e.name AS entity_name,
               r.timestamp AS cited_at
        """

        # Then get source chunks through Query->Chunk path
        chunks_query = """
        MATCH (q:Query {id: $response_id})-[:EXCERPTED_FROM]->(c:Chunk)
        RETURN c.id AS chunk_id,
               c.content AS content,
               c.parent_doc_id AS source_document
        """

        cited_entities: List[str] = []
        source_chunks: List[SourceChunk] = []

        async with self._driver.session(database=self._db) as session:
            # Get cited entities
            result_entities = await session.run(
                cast(LiteralString, entities_query),
                agent_id=agent_id,
                response_id=response_id,
            )
            entity_records = await result_entities.data()

            for record in entity_records:
                if record.get("entity_id"):
                    cited_entities.append(record["entity_id"])

            # Get source chunks
            result_chunks = await session.run(
                cast(LiteralString, chunks_query),
                response_id=response_id,
            )
            chunk_records = await result_chunks.data()

            for record in chunk_records:
                source_chunks.append(SourceChunk(
                    chunk_id=record.get("chunk_id", ""),
                    content=record.get("content", ""),
                    source_document=record.get("source_document", ""),
                ))

        # Calculate confidence based on cited entities and chunks
        confidence = min(1.0, (len(cited_entities) * 0.3 + len(source_chunks) * 0.7))

        return ProvenanceChain(
            response_id=response_id,
            agent_id=agent_id,
            cited_entities=cited_entities,
            source_chunks=source_chunks,
            confidence=confidence,
        )

    async def get_source_documents(
        self, agent_id: str, response_id: str
    ) -> List[SourceDocument]:
        """Get documents that contributed to the response.

        Traces from the agent through CITES relationships to entities,
        then to chunks, and finally to source documents.
        """
        query_cypher = """
        MATCH (a:Agent {id: $agent_id})-[r:CITES {response_id: $response_id}]->(e:Entity)
        MATCH (e)-[:EMBEDDED_IN|EXCERPTED_FROM*0..2]->(c:Chunk)
        MATCH (c)-[:PART_OF]->(d:Document)
        RETURN DISTINCT d.id AS document_id,
               d.title AS title,
               d.path AS path
        ORDER BY d.title
        """

        async with self._driver.session(database=self._db) as session:
            result = await session.run(
                cast(LiteralString, query_cypher),
                agent_id=agent_id,
                response_id=response_id,
            )
            records = await result.data()

        documents = []
        for record in records:
            documents.append(SourceDocument(
                document_id=record.get("document_id", ""),
                title=record.get("title", "Untitled"),
                path=record.get("path", ""),
            ))

        return documents

    async def get_cited_entities(
        self, agent_id: str, response_id: str
    ) -> List[str]:
        """Get list of entity IDs cited in a specific response."""
        query_cypher = """
        MATCH (a:Agent {id: $agent_id})-[r:CITES {response_id: $response_id}]->(e:Entity)
        RETURN e.id AS entity_id
        """

        async with self._driver.session(database=self._db) as session:
            result = await session.run(
                cast(LiteralString, query_cypher),
                agent_id=agent_id,
                response_id=response_id,
            )
            records = await result.data()

        return [r.get("entity_id", "") for r in records if r.get("entity_id")]


if __name__ == "__main__":
    import asyncio

    async def test():
        tracker = ProvenanceTracker()

        # Create test entities first
        from src.graph.graph_build import GraphBuilder

        builder = GraphBuilder(tracker._config)
        entity1 = await builder.create_entity(
            name="Test Entity 1",
            entity_type="CONCEPT",
            properties={"description": "First test entity"},
        )
        entity2 = await builder.create_entity(
            name="Test Entity 2",
            entity_type="CONCEPT",
            properties={"description": "Second test entity"},
        )
        print(f"Created entities: {entity1}, {entity2}")
        await builder.close()

        # Create a test agent
        from src.persona.agent_repository import AgentRepository
        from src.simulation.agent_node import AgentNode, Stance

        repo = AgentRepository(tracker._config)
        agent = AgentNode(
            name="Test Provenance Agent",
            archetype="TEST",
            stance=Stance.NEUTRAL,
        )
        created = await repo.create_agent(agent)
        agent_id = str(created.id)
        print(f"Created agent: {agent_id}")
        await repo.close()

        # Test cite_entity
        response_id = "test-response-001"
        await tracker.cite_entity(agent_id, entity1, response_id)
        await tracker.cite_entity(agent_id, entity2, response_id)
        print("Cited entities")

        # Test trace_response
        chain = await tracker.trace_response(agent_id, response_id)
        print(f"Provenance chain: {len(chain.cited_entities)} entities, "
              f"{len(chain.source_chunks)} chunks, confidence: {chain.confidence}")

        # Test get_cited_entities
        cited = await tracker.get_cited_entities(agent_id, response_id)
        print(f"Cited entities: {cited}")

        # Cleanup
        try:
            async with tracker._driver.session(database=tracker._db) as session:
                await session.run(
                    "MATCH (a:Agent {id: $id}) DETACH DELETE a",
                    id=agent_id
                )
                await session.run(
                    "MATCH (e:Entity {id: $id1}) DETACH DELETE e",
                    id1=str(entity1)
                )
                await session.run(
                    "MATCH (e:Entity {id: $id2}) DETACH DELETE e",
                    id2=str(entity2)
                )
        except Exception as e:
            print(f"Cleanup warning: {e}")

        await tracker.close()
        print("Done")

    asyncio.run(test())
