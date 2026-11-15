"""Graph Context Fetcher for agent prompts.

Provides methods to retrieve relevant entities and their context from the Neo4j graph.
"""

import asyncio
import inspect
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, LiteralString, Optional, cast
from uuid import UUID, uuid4

from llama_index.embeddings.ollama import OllamaEmbedding
from neo4j import AsyncGraphDatabase
from pydantic import BaseModel, Field

from src.billing.metering import MeteringError
from src.graph.config_graph import GraphConfig
from src.graph.neo4j_bootstrap import (
    CHUNK_EMBEDDINGS_INDEX,
    CHUNK_TEXT_INDEX,
    ENTITY_EMBEDDINGS_INDEX,
)
from src.graph.scope import chunk_in_dataset, entity_in_dataset
from src.llm.config_llm import LLMConfig
from src.persona.models_persona import ProvenanceLink

logger = logging.getLogger(__name__)

# The ollama clients default to httpx `timeout=None` (unbounded) — a stuck
# localhost embed call would wait forever. 60 s is a generous bound for it.
_EMBED_TIMEOUT_SECONDS = 60

# The vector index cannot pre-filter by dataset, so over-fetch and post-filter.
VECTOR_OVERFETCH = 5
# A chunk leg widens its fetch up to this many times the requested limit.
CHUNK_RECALL_CAP = 20

# Lucene query syntax, and the AND/OR/NOT words it reads as operators. Stripped
# from the user's question so it can never break or steer the fulltext query.
_LUCENE_SPECIAL = re.compile(r'[+\-&|!(){}\[\]^"~*?:\\/]')
_LUCENE_OPERATOR_WORDS = re.compile(r"\b(AND|OR|NOT)\b")

# One column list for both chunk legs, so a hit has the same shape from either.
_CHUNK_COLUMNS = (
    "node.chunk_id AS chunk_id, node.document_anchor AS doc_id, "
    "node.title AS doc_title, node.breadcrumb AS section, node.text AS text, "
    "CASE WHEN node IS NULL THEN [] ELSE "
    "[(node)-[:MENTIONS]->(e:__Entity__) WHERE e.id IS NOT NULL AND "
    f"{entity_in_dataset('e')} | e.id] END AS entity_ids"
)


# Store/base labels carried by every graph node — never the entity's real type.
_BASE_LABELS = {"__Entity__", "__Node__", "Chunk", "Document"}


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


@dataclass(frozen=True)
class ChunkHit:
    """A source chunk from one retrieval leg. `rank` is its 1-based position there."""

    chunk_id: str
    doc_id: str
    doc_title: str
    section: str
    text: str
    rank: int
    entity_ids: tuple[str, ...]


@dataclass(frozen=True)
class ChunkSearch:
    """The two ranked chunk legs, unfused: the synthesizer fuses them."""

    vector: List[ChunkHit]
    fulltext: List[ChunkHit]


def _lucene_terms(query: str) -> str:
    """The question as plain fulltext terms: no Lucene syntax, no operator words."""
    cleaned = _LUCENE_OPERATOR_WORDS.sub(" ", _LUCENE_SPECIAL.sub(" ", query))
    return " ".join(cleaned.split())


def _leg_cypher(procedure: str) -> str:
    """One chunk leg: the index's raw hits, post-filtered to the dataset, top `$limit`.

    `raw_hits` rides on every row. The sentinel (null node, score -2.0) always
    survives the filter, so a leg with no in-dataset hits still reports whether
    the index filled `$fetch`.
    """
    return f"""
    CALL {procedure}
    YIELD node, score
    WITH count(*) AS raw_hits, collect({{node: node, score: score}}) AS raw
    UNWIND (raw + [{{node: null, score: -2.0}}]) AS hit
    WITH raw_hits, hit.node AS node, hit.score AS leg_score
    WHERE node IS NULL OR {chunk_in_dataset("node")}
    RETURN raw_hits, {_CHUNK_COLUMNS}, leg_score
    ORDER BY leg_score DESC
    LIMIT $limit
    """


def _chunk_hits(rows: List[Dict[str, Any]]) -> List[ChunkHit]:
    hits: List[ChunkHit] = []
    for row in rows:
        if not row.get("chunk_id"):
            continue
        hits.append(
            ChunkHit(
                chunk_id=str(row["chunk_id"]),
                doc_id=row.get("doc_id") or "",
                doc_title=row.get("doc_title") or "",
                section=row.get("section") or "",
                text=row.get("text") or "",
                rank=len(hits) + 1,
                entity_ids=tuple(row.get("entity_ids") or ()),
            )
        )
    return hits


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
            model_name=LLMConfig.embedding_model,
            base_url=LLMConfig.ollama_base_url,
            client_kwargs={"timeout": _EMBED_TIMEOUT_SECONDS},
            ollama_additional_kwargs={"mirostat": 0},
        )

    @property
    def degraded(self) -> set[str]:
        """Capabilities a read could not use this run, e.g. "no_embeddings".

        Created per instance on first use, so an instance built without
        __init__ (the test doubles) cannot raise AttributeError on a failure path.
        """
        return vars(self).setdefault("_degraded", set())

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

    @staticmethod
    def _node_labels(node: Any, props: Dict[str, Any]) -> List[str]:
        """The entity's real type label(s): the neo4j Node's `.labels` minus the
        store/base labels, else `props["labels"]`, else ["Entity"]."""
        raw = None
        if hasattr(node, "labels"):
            raw = list(node.labels)
        elif isinstance(node, dict):
            raw = node.get("labels")
        labels = [str(l) for l in (raw or []) if str(l) not in _BASE_LABELS]
        return labels or ["Entity"]

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
        self, query: str, dataset_id: str, limit: int = 10
    ) -> List[EntityNode]:
        """Find the dataset's entity nodes most relevant to the query.

        Vector similarity on entity embeddings; over-fetches and post-filters by
        dataset, so a crowded-out dataset returns fewer rows, never another's.
        """
        query_vector = await self._get_embedding(query)

        cypher = f"""
        CALL db.index.vector.queryNodes('{ENTITY_EMBEDDINGS_INDEX}', $fetch, $vector)
        YIELD node, score AS vector_score
        WHERE {entity_in_dataset("node")}
        RETURN node, vector_score
        ORDER BY vector_score DESC
        LIMIT $limit
        """
        async with self._driver.session(database=self._db) as session:
            result = await session.run(
                cast(LiteralString, cypher),
                vector=query_vector,
                fetch=limit * VECTOR_OVERFETCH,
                limit=limit,
                dataset_id=dataset_id,
            )
            rows = await result.data()

        return [
            self._entity_from_node(row.get("node"), float(row.get("vector_score", 0.0)))
            for row in rows
            if row.get("node") is not None
        ]

    async def find_relevant_chunks(
        self, query: str, dataset_id: str, limit: int = 200
    ) -> ChunkSearch:
        """Dataset chunks for the query, as two ranked legs (fusion is the caller's).

        A question with no searchable terms returns nothing and reads nothing. The
        fulltext leg needs no embedding. If the query embedding fails, the vector
        leg is dropped and "no_embeddings" is recorded in `degraded`.
        """
        search = _lucene_terms(query)
        if not search:
            return ChunkSearch(vector=[], fulltext=[])
        fulltext = await self._recall_chunks(
            f"db.index.fulltext.queryNodes('{CHUNK_TEXT_INDEX}', $search, {{limit: $fetch}})",
            dataset_id,
            limit,
            search=search,
        )
        try:
            query_vector = await self._get_embedding(query)
        except MeteringError:
            raise
        except Exception as exc:
            logger.warning("Chunk vector leg skipped, no query embedding: %s", exc)
            self.degraded.add("no_embeddings")
            return ChunkSearch(vector=[], fulltext=fulltext)
        vector = await self._recall_chunks(
            f"db.index.vector.queryNodes('{CHUNK_EMBEDDINGS_INDEX}', $fetch, $vector)",
            dataset_id,
            limit,
            vector=query_vector,
        )
        return ChunkSearch(vector=vector, fulltext=fulltext)

    async def _recall_chunks(
        self, procedure: str, dataset_id: str, limit: int, **params: Any
    ) -> List[ChunkHit]:
        """Top `limit` dataset chunks from one index leg.

        The index cannot pre-filter by dataset, so `fetch` raw hits are taken and
        post-filtered. A leg whose raw hits filled `fetch` but kept fewer than
        `limit` widens (fetch doubles) until it has `limit`, the index runs out, or
        fetch reaches CHUNK_RECALL_CAP x limit, which is recorded in `degraded`.
        """
        cypher = cast(LiteralString, _leg_cypher(procedure))
        fetch = limit * VECTOR_OVERFETCH
        cap = limit * CHUNK_RECALL_CAP
        while True:
            async with self._driver.session(database=self._db) as session:
                result = await session.run(
                    cypher,
                    dataset_id=dataset_id,
                    fetch=fetch,
                    limit=limit,
                    **params,
                )
                rows = await result.data()
            hits = _chunk_hits(rows)
            raw_hits = (rows[0].get("raw_hits") or 0) if rows else 0
            if len(hits) >= limit or raw_hits < fetch:
                return hits
            if fetch >= cap:
                self.degraded.add("recall_capped")
                return hits
            fetch = min(fetch * 2, cap)

    def _entity_from_node(self, node: Any, relevance_score: float) -> EntityNode:
        """One EntityNode from a Neo4j node — the single node-reading body the
        vector search and the neighbour walk both construct through."""
        props = self._node_props(node)
        labels = self._node_labels(node, props)
        return EntityNode(
            id=str(props.get("id", props.get("name", uuid4()))),
            name=str(props.get("name", "Unknown")),
            label=labels[0],
            properties=props,
            relevance_score=relevance_score,
            summary=props.get("summary_context")
            or props.get("summary")
            or props.get("description"),
            domain_tags=self._parse_tags(props.get("domain_tags")),
        )

    async def find_connected_nodes(
        self, node_ids: List[str], dataset_id: str, limit: int = 25
    ) -> List[EntityNode]:
        """Entity nodes one relationship hop from the seed nodes.

        The roster-expansion walk for required-node derivation: seeds match by
        id or name (the same tolerance as `get_provenance`), the walk stays on
        entity-to-entity edges (`__Entity__`, never `Chunk`), and neighbours
        carry no vector score — relevance is 0.0, so selection ranks them on
        intent fit alone. Ordered by how many seeds reach a node; capped.
        """
        seed_ids = [str(node_id) for node_id in node_ids if str(node_id or "").strip()]
        if not seed_ids:
            return []

        cypher = f"""
        MATCH (seed:__Entity__)
        WHERE (seed.id IN $node_ids OR seed.name IN $node_ids)
          AND {entity_in_dataset("seed")}
        MATCH (seed)-[r]-(n:__Entity__)
        WHERE NOT n:Chunk
          AND NOT (n.id IN $node_ids OR n.name IN $node_ids)
          AND {entity_in_dataset("n")}
        WITH n, count(DISTINCT seed) AS seed_degree
        RETURN n, seed_degree
        ORDER BY seed_degree DESC
        LIMIT $limit
        """
        async with self._driver.session(database=self._db) as session:
            result = await session.run(
                cast(LiteralString, cypher),
                node_ids=seed_ids,
                dataset_id=dataset_id,
                limit=limit,
            )
            rows = await result.data()

        return [
            self._entity_from_node(row.get("n"), 0.0)
            for row in rows
            if row.get("n") is not None
        ]

    async def find_connected_nodes_by_seed(
        self, node_ids: List[str], dataset_id: str, limit: int = 10
    ) -> Dict[str, List[EntityNode]]:
        """Per-seed entity neighbours (entity↔entity only), keyed by seed id AND seed
        name so a caller resolving either key finds its group. One query.

        Seeds are not excluded as neighbours, so an edge between two seeds is read
        from both ends: this is how PageRank sees candidate-to-candidate edges. Each
        seed keeps at most `limit` neighbours, the strongest (most edges) first.
        A neighbour is listed once per key, however many edges join it to the seed.
        """
        keys = [str(n) for n in node_ids if str(n or "").strip()]
        if not keys:
            return {}

        cypher = f"""
        MATCH (seed:__Entity__)-[r]-(n:__Entity__)
        WHERE (seed.id IN $node_ids OR seed.name IN $node_ids)
          AND {entity_in_dataset("seed")}
          AND NOT n:Chunk AND n <> seed
          AND {entity_in_dataset("n")}
        WITH seed, n, count(r) AS weight
        ORDER BY seed.id, weight DESC, n.id
        WITH seed, collect(n)[..$per_seed] AS neighbours
        UNWIND neighbours AS n
        RETURN seed.id AS seed_id, seed.name AS seed_name, n
        """
        async with self._driver.session(database=self._db) as session:
            result = await session.run(
                cast(LiteralString, cypher),
                node_ids=keys,
                dataset_id=dataset_id,
                per_seed=limit,
            )
            rows = await result.data()

        grouped: Dict[str, List[EntityNode]] = {}
        seen: Dict[str, set[str]] = {}
        for row in rows:
            if row.get("n") is None:
                continue
            entity = self._entity_from_node(row.get("n"), 0.0)
            for key in (row.get("seed_id"), row.get("seed_name")):
                if key and entity.id not in seen.setdefault(str(key), set()):
                    seen[str(key)].add(entity.id)
                    grouped.setdefault(str(key), []).append(entity)
        return grouped

    async def find_entities_by_ids(
        self, entity_ids: List[str], dataset_id: str
    ) -> List[EntityNode]:
        """Dataset entities with the given ids, in one read (chunk-mentioned candidates).

        Unscored: relevance is 0.0, the caller takes relevance from the chunks.
        """
        ids = [str(entity_id) for entity_id in entity_ids if str(entity_id or "").strip()]
        if not ids:
            return []

        cypher = f"""
        MATCH (n:__Entity__)
        WHERE n.id IN $entity_ids AND NOT n:Chunk
          AND {entity_in_dataset("n")}
        RETURN n
        """
        async with self._driver.session(database=self._db) as session:
            result = await session.run(
                cast(LiteralString, cypher),
                entity_ids=ids,
                dataset_id=dataset_id,
            )
            rows = await result.data()

        return [
            self._entity_from_node(row.get("n"), 0.0)
            for row in rows
            if row.get("n") is not None
        ]

    def _parse_tags(self, tags: Any) -> List[str]:
        """Parse domain_tags from various formats."""
        if not tags:
            return []
        if isinstance(tags, list):
            return [str(t) for t in tags]
        if isinstance(tags, str):
            return [t.strip() for t in tags.split(",") if t.strip()]
        return []

    async def get_entity_context(
        self, entity_id: str, dataset_id: str
    ) -> Optional[EntityContext]:
        """Get complete context for an entity: itself, neighbors, and provenance."""
        entity = await self._get_entity_by_id(entity_id, dataset_id)
        if entity is None:
            return None

        neighbors = await self._get_neighbors(entity_id, dataset_id)
        provenance = await self.get_provenance(entity_id, dataset_id)

        return EntityContext(
            entity=entity,
            neighbors=neighbors,
            provenance=provenance,
        )

    async def _get_entity_by_id(
        self, entity_id: str, dataset_id: str
    ) -> Optional[EntityNode]:
        """Fetch a single entity by ID or name, within the dataset."""
        cypher = f"""
        MATCH (n)
        WHERE (n.id = $entity_id OR n.name = $entity_id)
          AND {entity_in_dataset("n")}
        RETURN n, labels(n)[0] AS label
        LIMIT 1
        """
        async with self._driver.session(database=self._db) as session:
            result = await session.run(
                cast(LiteralString, cypher),
                entity_id=entity_id,
                dataset_id=dataset_id,
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
            summary=props.get("summary_context")
            or props.get("summary")
            or props.get("description"),
            domain_tags=self._parse_tags(props.get("domain_tags")),
        )

    async def _get_neighbors(
        self, entity_id: str, dataset_id: str, limit: int = 10
    ) -> List[EntityNode]:
        """Fetch neighboring entities connected to the given entity, within the dataset."""
        cypher = f"""
        MATCH (n)-[r]-(m)
        WHERE (n.id = $entity_id OR n.name = $entity_id)
          AND {entity_in_dataset("n")}
        WITH m, type(r) AS rel_type, r.summary AS rel_summary
        WHERE m.name IS NOT NULL
          AND ({entity_in_dataset("m")} OR (m:Chunk AND {chunk_in_dataset("m")}))
        RETURN m, rel_type, rel_summary
        LIMIT $limit
        """
        async with self._driver.session(database=self._db) as session:
            result = await session.run(
                cast(LiteralString, cypher),
                entity_id=entity_id,
                dataset_id=dataset_id,
                limit=limit,
            )
            rows = await result.data()

        neighbors: List[EntityNode] = []
        for row in rows:
            node = row.get("m")
            if node is None:
                continue
            props = self._node_props(node)
            labels = self._node_labels(node, props)

            neighbors.append(
                EntityNode(
                    id=str(props.get("id", props.get("name", uuid4()))),
                    name=str(props.get("name", "Unknown")),
                    label=labels[0],
                    properties={
                        **props,
                        "relation_type": row.get("rel_type", ""),
                        "relation_summary": row.get("rel_summary", ""),
                    },
                    relevance_score=1.0,
                    summary=props.get("summary_context") or props.get("summary"),
                    domain_tags=self._parse_tags(props.get("domain_tags")),
                )
            )

        return neighbors

    async def get_provenance(
        self, entity_id: str, dataset_id: str
    ) -> List[ProvenanceLink]:
        """Return source chunks that contributed to the entity, within the dataset.

        Chunks point at the entities they mention (the llama-index store's
        direction), so an entity's provenance is its inbound MENTIONS. The
        source-document id lives on `document_anchor` — llama-index clobbers the
        generic `document_id`/`doc_id` properties to the sentinel `"None"`, so
        reading `doc_id` would return a fabricated id.
        """
        cypher = f"""
        MATCH (n)<-[:MENTIONS]-(chunk:Chunk)
        WHERE (n.id = $entity_id OR n.name = $entity_id)
          AND chunk.document_anchor IS NOT NULL
          AND {entity_in_dataset("n")}
          AND {chunk_in_dataset("chunk")}
        RETURN DISTINCT
            chunk.document_anchor AS doc_id,
            chunk.title AS title,
            chunk.breadcrumb AS breadcrumb,
            chunk.chunk_id AS chunk_id
        ORDER BY chunk.chunk_id
        """
        async with self._driver.session(database=self._db) as session:
            result = await session.run(
                cast(LiteralString, cypher),
                entity_id=entity_id,
                dataset_id=dataset_id,
            )
            rows = await result.data()

        provenance: List[ProvenanceLink] = []
        for row in rows:
            chunk_id = row.get("chunk_id")
            if chunk_id:
                try:
                    chunk_uuid = (
                        UUID(chunk_id) if isinstance(chunk_id, str) else chunk_id
                    )
                except (ValueError, TypeError):
                    chunk_uuid = uuid4()
            else:
                chunk_uuid = uuid4()

            provenance.append(
                ProvenanceLink(
                    doc_id=row.get("doc_id", ""),
                    title=row.get("title", "Unknown Source"),
                    breadcrumb=row.get("breadcrumb", ""),
                    chunk_id=chunk_uuid,
                )
            )

        return provenance

    async def get_provenance_batch(
        self, entity_ids: List[str], dataset_id: str
    ) -> Dict[str, List[ProvenanceLink]]:
        """Return source chunks for a whole roster in ONE query, within the dataset.

        Same per-entity result as `get_provenance` (a row reaches every
        requested key its node id or name matches, same chunk order), keyed by
        the requested id/name; entities with no chunks map to an empty list.
        """
        by_key: Dict[str, List[ProvenanceLink]] = {key: [] for key in entity_ids}
        if not by_key:
            return by_key

        cypher = f"""
        MATCH (n)<-[:MENTIONS]-(chunk:Chunk)
        WHERE (n.id IN $entity_ids OR n.name IN $entity_ids)
          AND chunk.document_anchor IS NOT NULL
          AND {entity_in_dataset("n")}
          AND {chunk_in_dataset("chunk")}
        RETURN DISTINCT
            n.id AS node_id,
            n.name AS node_name,
            chunk.document_anchor AS doc_id,
            chunk.title AS title,
            chunk.breadcrumb AS breadcrumb,
            chunk.chunk_id AS chunk_id
        ORDER BY chunk.chunk_id
        """
        async with self._driver.session(database=self._db) as session:
            result = await session.run(
                cast(LiteralString, cypher),
                entity_ids=list(by_key),
                dataset_id=dataset_id,
            )
            rows = await result.data()

        for row in rows:
            matched = {
                value
                for value in (row.get("node_id"), row.get("node_name"))
                if value is not None
            } & by_key.keys()
            if not matched:
                continue

            chunk_id = row.get("chunk_id")
            if chunk_id:
                try:
                    chunk_uuid = (
                        UUID(chunk_id) if isinstance(chunk_id, str) else chunk_id
                    )
                except (ValueError, TypeError):
                    chunk_uuid = uuid4()
            else:
                chunk_uuid = uuid4()

            link = ProvenanceLink(
                doc_id=row.get("doc_id", ""),
                title=row.get("title", "Unknown Source"),
                breadcrumb=row.get("breadcrumb", ""),
                chunk_id=chunk_uuid,
            )
            for key in matched:
                by_key[key].append(link)

        return by_key


# ---- Factory ----


def create_graph_context(config: Optional[GraphConfig] = None) -> GraphContext:
    """Create a GraphContext instance with optional config."""
    return GraphContext(config)


# ---- CLI Test ----

if __name__ == "__main__":
    import asyncio
    import sys

    async def test():
        config = GraphConfig()
        dataset_id = sys.argv[1]
        async with GraphContext(config) as ctx:
            entities = await ctx.find_relevant_entities(
                "AI ethics healthcare", dataset_id, limit=5
            )
            print(f"Found {len(entities)} relevant entities")
            for e in entities:
                print(f"  - {e.name} ({e.label}): score={e.relevance_score:.3f}")

            if entities:
                entity_id = entities[0].id
                context = await ctx.get_entity_context(entity_id, dataset_id)
                if context:
                    print(f"\nContext for {context.entity.name}:")
                    print(f"  Neighbors: {len(context.neighbors)}")
                    print(f"  Provenance: {len(context.provenance)}")

    asyncio.run(test())
