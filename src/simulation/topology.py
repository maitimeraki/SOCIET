"""
CommunicationTopology: Cypher-based pair scoring using Neo4j graph.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List

from src.simulation.pair_turn import CommPair

if TYPE_CHECKING:
    from neo4j import AsyncGraphDatabase
    from src.persona.agent import Agent
    from src.simulation.debate_config import DebateConfig


class CommunicationTopology:
    """Computes agent communication pairs via Cypher queries against Neo4j."""

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
        Round 2+: Expand path length to per-agent `communication_radius`
                  (capped by `config.comm_radius`). Previously the agent's
                  own radius was ignored; this was Gap P15.
        """
        agent_names = [p.identity.name for p in profiles]
        # Per-agent radius takes precedence, capped by the global config ceiling.
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
        """Cypher for round 2+: multi-hop paths up to the agent's communication_radius.

        `effective_radius` is a Python int already clamped to [1, config.comm_radius]
        by the caller. We interpolate it via Cypher's `*1..N` syntax, which only
        accepts integers -- the caller-side clamp is what makes this safe.
        """
        radius = effective_radius

        cypher = f"""
        MATCH (a:Persona)-[r1*1..{radius}]-(e)-[r2*1..{radius}]-(b:Persona)
        WHERE a.name IN $agent_names AND b.name IN $agent_names
          AND a <> b
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

