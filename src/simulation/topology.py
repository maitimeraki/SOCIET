"""
CommunicationTopology: Cypher-based pair scoring using Neo4j graph.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List
from src.simulation.communication_graph import CommPair

if TYPE_CHECKING:
    from neo4j import AsyncGraphDatabase
    from src.persona.models_persona import AgentProfile
    from src.simulation.debate_config import DebateConfig




class CommunicationTopology:
    """Computes agent communication pairs via Cypher queries against Neo4j."""

    def __init__(self, driver: "AsyncGraphDatabase", db: str):
        self._driver = driver
        self._db = db

    async def compute_round_pairs(
        self,
        profiles: List["AgentProfile"],
        dataset_id: str,
        round_num: int,
        config: "DebateConfig",
    ) -> List[CommPair]:
        """
        Compute communication pairs for a debate round using Cypher.

        Round 1: Direct entity overlap via single-hop paths.
        Round 2+: Expand path length to comm_radius hops.
        """
        agent_names = [p.identity.name for p in profiles]

        async with self._driver.session(database=self._db) as session:
            if round_num == 1:
                cypher, params = self._round1_cypher(agent_names, dataset_id, config)
            else:
                cypher, params = self._round_n_cypher(
                    agent_names, dataset_id, config, round_num
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
        """Generate Cypher for round 1: single-hop entity sharing."""
        cypher = """
        MATCH (a:Persona)-[r1]-(e)-[r2]-(b:Persona)
        WHERE a.name IN $agent_names AND b.name IN $agent_names
          AND a <> b
          AND coalesce(a.dataset_id, '') = $dataset_id
        WITH a, b, count(DISTINCT e) AS shared_count,
             collect(DISTINCT e.name) AS shared_entities
        WHERE shared_count >= 1
        WITH a, b, shared_count, shared_entities,
             size(a.domain_tags) AS tags_a, size(b.domain_tags) AS tags_b
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
        round_num: int,
    ) -> tuple[str, dict]:
        """Generate Cypher for round 2+: multi-hop paths up to comm_radius."""
        radius = config.comm_radius

        cypher = f"""
        MATCH (a:Persona)-[r1*1..{radius}]-(e)-[r2*1..{radius}]-(b:Persona)
        WHERE a.name IN $agent_names AND b.name IN $agent_names
          AND a <> b
          AND coalesce(a.dataset_id, '') = $dataset_id
        WITH a, b, count(DISTINCT e) AS shared_count,
             collect(DISTINCT e.name) AS shared_entities
        WHERE shared_count >= 1
        WITH a, b, shared_count, shared_entities,
             size(a.domain_tags) AS tags_a, size(b.domain_tags) AS tags_b
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
