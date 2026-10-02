"""
CommunicationTopology: Cypher-based pair scoring using Neo4j graph.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List

from src.simulation.pair_turn import ActivationCandidate, CommPair

if TYPE_CHECKING:
    from neo4j import AsyncGraphDatabase
    from src.persona.agent import Agent
    from src.simulation.debate_config import DebateConfig


class CommunicationTopology:
    """Computes agent communication pairs via Cypher queries against Neo4j.

    The pairing/activation patterns score *entity* overlap, so their untyped
    middle node carries an explicit `NOT e:Chunk` guard: the graph also holds
    `(Persona)-[:MENTIONS]->(Chunk)` provenance edges, and without the guard a
    shared source chunk would count as a shared entity (and, having no `name`,
    would contribute an empty `shared_entities` entry).
    """

    def __init__(self, driver: "AsyncGraphDatabase", db: str):
        self._driver = driver
        self._db = db

    async def compute_round_pairs(
        self,
        profiles: List["Agent"],
        dataset_id: str,
        round_num: int,
        config: "DebateConfig",
    ) -> List[CommPair]:
        """
        Compute communication pairs for a debate round using Cypher.

        Round 1: Direct entity overlap via single-hop paths.
        Round 2+: Expand path length to one cohort-wide radius: `max()` over
                  every agent's own `communication_radius`, clamped to
                  [1, `config.comm_radius`]. One wide-radius agent widens the
                  path for every pair.
        """
        agent_names = [p.identity.name for p in profiles]
        # One cohort-wide radius: the widest agent's own radius governs every
        # pair, clamped to [1, config.comm_radius].
        per_agent_radius = max(
            (getattr(p, "communication_radius", 1) for p in profiles),
            default=1,
        )
        effective_radius = max(1, min(int(per_agent_radius), int(config.comm_radius)))

        async with self._driver.session(database=self._db) as session:
            if round_num == 1:
                cypher, params = self._round1_cypher(agent_names, dataset_id, config)
            else:
                cypher, params = self._round_n_cypher(
                    agent_names, dataset_id, config, effective_radius
                )

            result = await session.run(cypher, **params)
            records = await result.data()
            return self._parse_comm_pairs(records)

    def _round1_cypher(
        self,
        agent_names: List[str],
        dataset_id: str,
        config: "DebateConfig",
    ) -> tuple[str, dict]:
        """Cypher for round 1: single-hop entity sharing (Jaccard + OPPOSES/SUPPORTS)."""
        cypher = """
        MATCH (a:Persona)-[r1]-(e)-[r2]-(b:Persona)
        WHERE a.name IN $agent_names AND b.name IN $agent_names
          AND a <> b
          AND NOT e:Chunk
          AND coalesce(a.dataset_id, '') = $dataset_id
        WITH a, b, count(DISTINCT e) AS shared_count,
             collect(DISTINCT e.name) AS shared_entities
        WHERE shared_count >= 1
        WITH a, b, shared_count, shared_entities,
             size(coalesce(a.domain_tags, [])) AS tags_a,
             size(coalesce(b.domain_tags, [])) AS tags_b
        WITH a, b, shared_count, shared_entities,
             toFloat(shared_count) / toFloat(tags_a + tags_b - shared_count) AS jaccard,
             exists((a)-[:OPPOSES]-(b)) AS has_opposes,
             exists((a)-[:SUPPORTS]-(b)) AS has_supports
        WITH a, b, shared_count, shared_entities,
             jaccard + CASE
               WHEN has_opposes THEN 0.3
               WHEN has_supports THEN 0.2
               ELSE 0.0
             END AS score
        WHERE score >= $threshold
        RETURN a.name AS agent_a, b.name AS agent_b, shared_entities, score
        ORDER BY score DESC
        LIMIT $max_pairs
        """
        params = {
            "agent_names": agent_names,
            "dataset_id": dataset_id,
            "threshold": config.topology_score_threshold,
            "max_pairs": config.max_pairs_per_round,
        }
        return cypher, params

    def _round_n_cypher(
        self,
        agent_names: List[str],
        dataset_id: str,
        config: "DebateConfig",
        effective_radius: int,
    ) -> tuple[str, dict]:
        """Cypher for round 2+: multi-hop paths up to a single cohort-wide radius.

        The round emits one query for every pair, so there is one radius for the
        whole cohort: `effective_radius` is `max()` over all agents' own
        `communication_radius` (clamped to [1, config.comm_radius]) -- one
        wide-radius agent widens the path for every pair.

        `effective_radius` is a Python int already clamped by the caller. We
        interpolate it via Cypher's `*1..N` syntax, which only accepts integers
        -- the caller-side clamp is what makes this safe.
        """
        radius = effective_radius

        cypher = f"""
        MATCH (a:Persona)-[r1*1..{radius}]-(e)-[r2*1..{radius}]-(b:Persona)
        WHERE a.name IN $agent_names AND b.name IN $agent_names
          AND a <> b
          AND NOT e:Chunk
          AND coalesce(a.dataset_id, '') = $dataset_id
        WITH a, b, count(DISTINCT e) AS shared_count,
             collect(DISTINCT e.name) AS shared_entities
        WHERE shared_count >= 1
        WITH a, b, shared_count, shared_entities,
             size(coalesce(a.domain_tags, [])) AS tags_a,
             size(coalesce(b.domain_tags, [])) AS tags_b
        WITH a, b, shared_count, shared_entities,
             toFloat(shared_count) / toFloat(tags_a + tags_b - shared_count) AS jaccard,
             exists((a)-[:OPPOSES]-(b)) AS has_opposes,
             exists((a)-[:SUPPORTS]-(b)) AS has_supports
        WITH a, b, shared_count, shared_entities,
             jaccard + CASE
               WHEN has_opposes THEN 0.3
               WHEN has_supports THEN 0.2
               ELSE 0.0
             END AS score
        WHERE score >= $threshold
        RETURN a.name AS agent_a, b.name AS agent_b, shared_entities, score
        ORDER BY score DESC
        LIMIT $max_pairs
        """
        params = {
            "agent_names": agent_names,
            "dataset_id": dataset_id,
            "threshold": config.topology_score_threshold,
            "max_pairs": config.max_pairs_per_round,
        }
        return cypher, params

    _ACTIVATION_MENTIONS_CYPHER = """
    MATCH (o:Opinion {dataset_id: $ds, query_hash: $qh, round_no: $last_round})-[:MENTIONS]->(e)
    MATCH (p:Persona)
    WHERE coalesce(p.dataset_id, '') = $ds
      AND NOT p.name IN $participants
      AND (e.name IN coalesce(p.entity_affinity, []) OR e.name IN coalesce(p.domain_tags, []))
    WITH p, collect(DISTINCT e.name) AS shared
    WHERE size(shared) > 0
    RETURN p.name AS name, shared
    ORDER BY size(shared) DESC
    LIMIT $limit
    """

    _ACTIVATION_ADJACENCY_CYPHER = """
    MATCH (p:Persona)-[r1]-(e)-[r2]-(part:Persona)
    WHERE part.name IN $participants
      AND coalesce(p.dataset_id, '') = $ds
      AND coalesce(part.dataset_id, '') = $ds
      AND p <> part
      AND NOT e:Chunk
      AND NOT p.name IN $participants
    WITH p, count(DISTINCT e) AS shared_count, collect(DISTINCT e.name) AS shared_entities
    WHERE shared_count >= 1
    RETURN p.name AS name, shared_entities
    ORDER BY shared_count DESC
    LIMIT $limit
    """

    async def find_activation_candidates(
        self,
        participants: List[str],
        dataset_id: str,
        query_hash: str,
        last_round: int,
        max_new: int,
    ) -> List["ActivationCandidate"]:
        """Agents outside the debate that should be pulled in after a round.

        Source 1: entities named in the round's committed opinions matched
        against persona entity_affinity / domain_tags.
        Source 2: personas sharing single-hop entity paths with participants
        (same scoring family as round-1 pairing).
        """
        if max_new <= 0 or not participants:
            return []

        async with self._driver.session(database=self._db) as session:
            rows_m = await (await session.run(
                self._ACTIVATION_MENTIONS_CYPHER,
                ds=dataset_id, qh=query_hash, last_round=last_round,
                participants=participants, limit=max_new,
            )).data()
            rows_a = await (await session.run(
                self._ACTIVATION_ADJACENCY_CYPHER,
                ds=dataset_id, participants=participants, limit=max_new,
            )).data()

        merged: dict[str, ActivationCandidate] = {}
        for r in rows_m:
            merged[r["name"]] = ActivationCandidate(
                agent_name=r["name"],
                shared_entities=list(r.get("shared") or []),
                reason="mentioned entity in the debate",
            )
        for r in rows_a:
            if r["name"] not in merged:
                merged[r["name"]] = ActivationCandidate(
                    agent_name=r["name"],
                    shared_entities=list(r.get("shared_entities") or []),
                    reason="shares entities with the active debate",
                )
        ranked = sorted(merged.values(), key=lambda c: len(c.shared_entities), reverse=True)
        return ranked[:max_new]

    def _parse_comm_pairs(self, records: list) -> List[CommPair]:
        """Parse Neo4j records into CommPair objects."""
        pairs = []
        for record in records:
            pair = CommPair(
                agent_a=record["agent_a"],
                agent_b=record["agent_b"],
                shared_entities=record.get("shared_entities", []),
                score=record.get("score", 0.0),
            )
            pairs.append(pair)
        return pairs

