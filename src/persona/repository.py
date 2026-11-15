from typing import Any, Dict, List, LiteralString, Optional, Sequence, cast

from llama_index.embeddings.ollama import OllamaEmbedding
from neo4j import AsyncGraphDatabase

from src.graph.scope import chunk_in_dataset, entity_in_dataset
from src.llm.config_llm import LLMConfig
from src.logging.setup_logging import setup_logging

logger = setup_logging()

# The ollama clients default to httpx `timeout=None` (unbounded) — a stuck
# localhost embed call would wait forever. 60 s is a generous bound for it.
_EMBED_TIMEOUT_SECONDS = 60


# Store/base labels carried by every graph node — never the entity's real type.
# Mirrors `graph_context._BASE_LABELS`; the type is a Neo4j label, not a property.
_BASE_LABELS = frozenset({"__Entity__", "__Node__", "Chunk", "Document"})


def _real_type_label(labels: Any) -> str:
    """The first non-base Neo4j label a node carries, or "" when it has none."""
    for label in labels or ():
        text = str(label).strip()
        if text and text not in _BASE_LABELS:
            return text
    return ""

class PersonaRepository:
    def __init__(
        self,
        neo4j_uri: str,
        neo4j_user: str,
        neo4j_password: str,
        neo4j_database: str,
        llm_client: Any | None = None,
    ):
        self.llm_client = llm_client
        self.embed_model = OllamaEmbedding(
            model_name=LLMConfig.embedding_model,
            base_url=LLMConfig.ollama_base_url,
            client_kwargs={"timeout": _EMBED_TIMEOUT_SECONDS},
            ollama_additional_kwargs={"mirostat": 0},
        )
        self._driver = AsyncGraphDatabase.driver(
            neo4j_uri,
            auth=(neo4j_user, neo4j_password),
        )
        self._db = neo4j_database

    async def close(self) -> None:
        await self._driver.close()

    @staticmethod
    def _node_props(node: Any) -> Dict[str, Any]:
        """Safely read node properties from various neo4j driver node representations."""
        if node is None:
            return {}
        try:
            # mapping-like object (recorded dict)
            if isinstance(node, dict):
                return dict(node)
            # py2neo-style or neo4j node with ._properties
            if hasattr(node, "_properties"):
                return dict(node._properties)
            # neo4j v5 node has .properties
            if hasattr(node, "properties"):
                return dict(node.properties)
            # fallback: cast to dict
            return dict(node)
        except Exception:
            logger.exception("Failed to read node properties")
            return {}

    async def fetch_nodes_by_names(
        self, names: List[str], dataset_id: str
    ) -> Dict[str, Dict[str, Any]]:
        """Batch-fetch entity nodes by their `name` property and return a map name->props.

        Only `:__Entity__` nodes of `dataset_id` match (audit C1). Persona nodes
        carry no entity label, so a persona's own properties never shadow an
        entity's (`triplet_source_id` etc.).
        """
        if not names:
            return {}

        query = f"""
        MATCH (n:__Entity__)
        WHERE n.name IN $names AND {entity_in_dataset("n")}
        RETURN n.name AS name, n, labels(n) AS labels
        """
        async with self._driver.session(database=self._db) as session:
            res = await session.run(
                cast(LiteralString, query), names=names, dataset_id=dataset_id
            )
            rows = await res.data()

        out: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            name = r.get("name")
            node = r.get("n")
            if not node or not name:
                continue
            props = self._node_props(node)
            # A node's real type is a Neo4j label, never a property, so a
            # props-only read drops it. Carry it as `label` so the build's
            # Task 5 identity precedence (`node["label"]`) can derive the
            # archetype — joiners reach the build through this fetch alone.
            label = _real_type_label(r.get("labels"))
            if label and not props.get("label"):
                props = {**props, "label": label}
            out.setdefault(name, props)
        return out

    #: Bound on the provenance write: at most this many chunk ids per persona, per call.
    _PROVENANCE_CHUNK_CAP = 20

    async def write_persona_provenance(
        self,
        persona_name: str,
        dataset_id: str,
        chunk_node_ids: Sequence[str],
    ) -> int:
        """D2: write the `(Persona)-[:MENTIONS]->(Chunk)` edges `get_provenance` reads.

        `chunk_node_ids` are graph chunk node ids — each entity's
        `triplet_source_id`. Ids are stripped, deduped and capped at
        `_PROVENANCE_CHUNK_CAP`, then written in ONE idempotent statement; empty
        input issues no query and returns 0. The Persona MERGE keys match
        `SocietyMemory.commit_round` exactly, so this composes with the
        round-commit node instead of shadowing it. Returns the number of edges
        ensured (ids with no matching chunk node are skipped).
        """
        chunk_ids = list(
            dict.fromkeys(
                str(cid).strip() for cid in chunk_node_ids if str(cid or "").strip()
            )
        )[: self._PROVENANCE_CHUNK_CAP]
        if not chunk_ids:
            return 0

        cypher = f"""
        UNWIND $chunk_ids AS cid
        MATCH (c:__Node__ {{id: cid}})
        WHERE {chunk_in_dataset("c")}
        MERGE (p:Persona {{name: $name, dataset_id: $dataset_id}})
        MERGE (p)-[:MENTIONS]->(c)
        RETURN count(*) AS written
        """

        async with self._driver.session(database=self._db) as session:
            result = await session.run(
                cypher,
                chunk_ids=chunk_ids,
                name=persona_name,
                dataset_id=dataset_id,
            )
            rows = await result.data()

        return int(rows[0]["written"]) if rows else 0

    async def write_persona_entity_links(
        self,
        persona_name: str,
        dataset_id: str,
        chunk_node_ids: Sequence[str],
        stance: Optional[str] = None,
    ) -> int:
        """Write the `(Persona)-[:MENTIONS]->(__Entity__)` edges the topology counts.

        Round-1 pair scoring counts shared non-Chunk middle nodes between two
        personas; without these edges every synthesized persona is an isolated
        node and no pair can ever score. The linked entities are those mentioned
        by the persona's source chunks — the content the persona was synthesized
        from. The same statement (re)writes `domain_tags`/`entity_affinity` to
        the linked entity names: the vocabulary both the pair scorer's Jaccard
        denominator and the activation reader consume. When `stance` is supplied
        it is also written to the node — Task 6's round-1 pairing reads
        `Persona.stance` before any opinion exists; `None` leaves the stored
        value untouched. Idempotent, bounded, and tolerant exactly like
        `write_persona_provenance`.
        """
        chunk_ids = list(
            dict.fromkeys(
                str(cid).strip() for cid in chunk_node_ids if str(cid or "").strip()
            )
        )[: self._PROVENANCE_CHUNK_CAP]
        if not chunk_ids:
            return 0

        cypher = f"""
        UNWIND $chunk_ids AS cid
        MATCH (c:__Node__ {{id: cid}})-[:MENTIONS]->(e:__Entity__)
        WHERE {chunk_in_dataset("c")} AND {entity_in_dataset("e")}
        WITH DISTINCT e
        MERGE (p:Persona {{name: $name, dataset_id: $dataset_id}})
        MERGE (p)-[:MENTIONS]->(e)
        WITH p, collect(DISTINCT e.name) AS names
        WHERE size(names) > 0
        SET p.domain_tags = names, p.entity_affinity = names,
            p.stance = coalesce($stance, p.stance)
        RETURN size(names) AS linked
        """

        async with self._driver.session(database=self._db) as session:
            result = await session.run(
                cypher,
                chunk_ids=chunk_ids,
                name=persona_name,
                dataset_id=dataset_id,
                stance=stance,
            )
            rows = await result.data()

        return int(rows[0]["linked"]) if rows else 0
