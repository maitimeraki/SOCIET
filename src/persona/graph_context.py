"""Graph Context Fetcher for agent prompts.

Provides methods to retrieve relevant entities and their context from the Neo4j graph.
"""
import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, cast, LiteralString

from neo4j import AsyncGraphDatabase
from llama_index.embeddings.ollama import OllamaEmbedding
from pydantic import BaseModel, Field
from uuid import UUID, uuid4

from src.graph.config_graph import GraphConfig
from src.persona.models_persona import ProvenanceLink


# ---- Supporting Types ----

class EntityNode(BaseModel):
    """A graph entity node with properties and relevance score."""
    id: str
    name: str
    label: str
    properties: Dict[str, Any] = Field(default_factory=dict)
    relevance_score: float = 0.0
    summary: Optional[str] = None
    domain_tags: List[str] = Field(default_factory=list)


@dataclass
class EntityContext:
    """Complete context for an entity: the entity itself, its neighbors, and provenance."""
    entity: EntityNode
    neighbors: List[EntityNode]
    provenance: List[ProvenanceLink]


# ---- GraphContext ----

class GraphContext:
    """Fetches relevant graph context for agent prompts.

    Uses Neo4j for graph traversal and Ollama embeddings for vector similarity search.
    """

    def __init__(self, config: Optional[GraphConfig] = None):
        self.config = config or GraphConfig()
        self._driver = AsyncGraphDatabase.driver(
            self.config.neo4j_uri,
            auth=(self.config.neo4j_username, self.config.neo4j_password),
        )
        self._db = self.config.neo4j_database
        self._embed_model = OllamaEmbedding(
            model_name="nomic-embed-text:v1.5",
            base_url="http://localhost:11434",
            ollama_additional_kwargs={"mirostat": 0},
        )

    async def close(self) -> None:
        """Close the Neo4j driver."""
        await self._driver.close()

    async def __aenter__(self) -> "GraphContext":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    @staticmethod
    def _node_props(node: Any) -> Dict[str, Any]:
        """Safely read node properties from various neo4j driver representations."""
        if node is None:
            return {}
        try:
            if isinstance(node, dict):
                return dict(node)
            if hasattr(node, "_properties"):
                return dict(node._properties)
            if hasattr(node, "properties"):
                return dict(node.properties)
            return dict(node)
        except Exception:
            return {}

    async def _get_embedding(self, text: str) -> List[float]:
        """Get embedding for text using Ollama."""
        func = None
        for name in ("get_embedding", "get_text_embedding", "embed", "encode"):
            if hasattr(self._embed_model, name):
                func = getattr(self._embed_model, name)
                break
        if func is None:
            raise RuntimeError("Embedding provider has no recognizable method")
        if inspect.iscoroutinefunction(func):
            return await func(text)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, text)

    async def find_relevant_entities(
        self, query: str, limit: int = 10
    ) -> List[EntityNode]:
        """Find entity nodes most relevant to the query using hybrid search.

        Uses vector similarity on entity embeddings combined with keyword matching.
        """
        query_vector = await self._get_embedding(query)

        cypher = """
        CALL db.index.vector.queryNodes('entity_embeddings', $limit, $vector)
        YIELD node, score AS vector_score
        RETURN node, vector_score
        ORDER BY vector_score DESC
        LIMIT $limit
        """
        async with self._driver.session(database=self._db) as session:
            result = await session.run(
                cast(LiteralString, cypher),
                vector=query_vector,
                limit=limit,
            )
            rows = await result.data()

        entities: List[EntityNode] = []
        for row in rows:
            node = row.get("node")
            if node is None:
                continue
            props = self._node_props(node)
            labels = list(node.keys()) if hasattr(node, "keys") else props.get("labels", ["Entity"])

            entities.append(EntityNode(
                id=str(props.get("id", props.get("name", uuid4()))),
                name=str(props.get("name", "Unknown")),
                label=labels[0] if labels else "Entity",
                properties=props,
                relevance_score=float(row.get("vector_score", 0.0)),
                summary=props.get("summary_context") or props.get("summary") or props.get("description"),
                domain_tags=self._parse_tags(props.get("domain_tags")),
            ))

        return entities

    def _parse_tags(self, tags: Any) -> List[str]:
        """Parse domain_tags from various formats."""
        if not tags:
            return []
        if isinstance(tags, list):
            return [str(t) for t in tags]
        if isinstance(tags, str):
            return [t.strip() for t in tags.split(",") if t.strip()]
        return []

    async def get_entity_context(self, entity_id: str) -> Optional[EntityContext]:
        """Get complete context for an entity: itself, neighbors, and provenance."""
        entity = await self._get_entity_by_id(entity_id)
        if entity is None:
            return None

        neighbors = await self._get_neighbors(entity_id)
        provenance = await self.get_provenance(entity_id)

        return EntityContext(
            entity=entity,
            neighbors=neighbors,
            provenance=provenance,
        )

    async def _get_entity_by_id(self, entity_id: str) -> Optional[EntityNode]:
        """Fetch a single entity by ID or name."""
        cypher = """
        MATCH (n)
        WHERE n.id = $entity_id OR n.name = $entity_id
        RETURN n, labels(n)[0] AS label
        LIMIT 1
        """
        async with self._driver.session(database=self._db) as session:
            result = await session.run(
                cast(LiteralString, cypher),
                entity_id=entity_id,
            )
            row = await result.single()

        if not row:
            return None

        node = row.get("n")
        props = self._node_props(node)
        label = row.get("label") or "Entity"

        return EntityNode(
            id=str(entity_id),
            name=str(props.get("name", entity_id)),
            label=label,
            properties=props,
            relevance_score=1.0,
            summary=props.get("summary_context") or props.get("summary") or props.get("description"),
            domain_tags=self._parse_tags(props.get("domain_tags")),
        )

    async def _get_neighbors(self, entity_id: str, limit: int = 10) -> List[EntityNode]:
        """Fetch neighboring entities connected to the given entity."""
        cypher = """
        MATCH (n)-[r]-(m)
        WHERE n.id = $entity_id OR n.name = $entity_id
        WITH m, type(r) AS rel_type, r.summary AS rel_summary
        WHERE m.name IS NOT NULL
        RETURN m, rel_type, rel_summary
        LIMIT $limit
        """
        async with self._driver.session(database=self._db) as session:
            result = await session.run(
                cast(LiteralString, cypher),
                entity_id=entity_id,
                limit=limit,
            )
            rows = await result.data()

        neighbors: List[EntityNode] = []
        for row in rows:
            node = row.get("m")
            if node is None:
                continue
            props = self._node_props(node)
            labels = list(node.keys()) if hasattr(node, "keys") else props.get("labels", ["Entity"])

            neighbors.append(EntityNode(
                id=str(props.get("id", props.get("name", uuid4()))),
                name=str(props.get("name", "Unknown")),
                label=labels[0] if labels else "Entity",
                properties={**props, "relation_type": row.get("rel_type", ""), "relation_summary": row.get("rel_summary", "")},
                relevance_score=1.0,
                summary=props.get("summary_context") or props.get("summary"),
                domain_tags=self._parse_tags(props.get("domain_tags")),
            ))

        return neighbors

    async def get_provenance(self, entity_id: str) -> List[ProvenanceLink]:
        """Return source chunks that contributed to the entity.

        Traces back through MENTIONS relationships to Chunk nodes.
        """
        cypher = """
        MATCH (n)-[:MENTIONS]->(chunk:Chunk)
        WHERE n.id = $entity_id OR n.name = $entity_id
        AND chunk.doc_id IS NOT NULL
        RETURN DISTINCT
            chunk.doc_id AS doc_id,
            chunk.title AS title,
            chunk.breadcrumb AS breadcrumb,
            chunk.chunk_id AS chunk_id
        ORDER BY chunk.chunk_id
        """
        async with self._driver.session(database=self._db) as session:
            result = await session.run(
                cast(LiteralString, cypher),
                entity_id=entity_id,
            )
            rows = await result.data()

        provenance: List[ProvenanceLink] = []
        for row in rows:
            chunk_id = row.get("chunk_id")
            if chunk_id:
                try:
                    chunk_uuid = UUID(chunk_id) if isinstance(chunk_id, str) else chunk_id
                except (ValueError, TypeError):
                    chunk_uuid = uuid4()
            else:
                chunk_uuid = uuid4()

            provenance.append(ProvenanceLink(
                doc_id=row.get("doc_id", ""),
                title=row.get("title", "Unknown Source"),
                breadcrumb=row.get("breadcrumb", ""),
                chunk_id=chunk_uuid,
            ))

        return provenance


# ---- Factory ----

def create_graph_context(config: Optional[GraphConfig] = None) -> GraphContext:
    """Create a GraphContext instance with optional config."""
    return GraphContext(config)


# ---- CLI Test ----

if __name__ == "__main__":
    import asyncio

    async def test():
        config = GraphConfig()
        async with GraphContext(config) as ctx:
            entities = await ctx.find_relevant_entities("AI ethics healthcare", limit=5)
            print(f"Found {len(entities)} relevant entities")
            for e in entities:
                print(f"  - {e.name} ({e.label}): score={e.relevance_score:.3f}")

            if entities:
                entity_id = entities[0].id
                context = await ctx.get_entity_context(entity_id)
                if context:
                    print(f"\nContext for {context.entity.name}:")
                    print(f"  Neighbors: {len(context.neighbors)}")
                    print(f"  Provenance: {len(context.provenance)}")

    asyncio.run(test())
