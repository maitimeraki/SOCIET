from typing import Any, Optional, Sequence

from llama_index.embeddings.ollama import OllamaEmbedding
from neo4j import AsyncGraphDatabase

from src.graph.scope import chunk_in_dataset, entity_in_dataset
from src.llm.config_llm import LLMConfig

# The ollama clients default to httpx `timeout=None` (unbounded) — a stuck
# localhost embed call would wait forever. 60 s is a generous bound for it.
_EMBED_TIMEOUT_SECONDS = 60


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
