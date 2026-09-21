"""ProfileSynthesizer: Graph-backed agent profile synthesis from entity clusters."""
import math
from collections import defaultdict
from typing import Any

from src.persona.graph_context import GraphContext, EntityNode
from src.persona.models_persona import AgentProfile
from src.persona.repository import PersonaRepository


class ProfileSynthesizer:
    """Synthesizes AgentProfiles from graph entity clusters using sector discovery."""

    def __init__(self, persona_repo: PersonaRepository, graph_context: GraphContext):
        self._repo = persona_repo
        self._ctx = graph_context

    async def synthesize(
        self, query: str, dataset_id: str, max_agents: int = 5
    ) -> list[AgentProfile]:
        """Synthesize agent profiles from relevant graph entities.

        1. Vector-search entities by query
        2. Group entities by shared chunk provenance (co-occurrence clustering)
        3. Sort clusters by aggregate relevance
        4. Take top clusters (adaptive count)
        5. Build AgentProfile for each cluster representative
        """
        # Adaptive target: sqrt(n) * 4, capped at max_agents
        search_limit = max_agents * 3
        entities = await self._ctx.find_relevant_entities(query, limit=search_limit)
        relevant_entity_count = len(entities)
        target = min(max_agents, int(math.sqrt(relevant_entity_count) * 4))

        if not entities:
            return []

        # Group entities by provenance (entities sharing same source chunks cluster together)
        clusters: dict[str, list[EntityNode]] = defaultdict(list)
        for entity in entities:
            # Use entity id as cluster key (each entity is its own cluster)
            # Provenance-based grouping would require fetching context for each entity
            clusters[entity.id].append(entity)

        # Sort clusters by aggregate relevance score
        cluster_scores = []
        for cluster_id, cluster_entities in clusters.items():
            total_relevance = sum(e.relevance_score for e in cluster_entities)
            cluster_scores.append((cluster_id, cluster_entities, total_relevance))

        cluster_scores.sort(key=lambda x: x[2], reverse=True)
        top_clusters = cluster_scores[:target]

        # Build profiles for each cluster
        profiles: list[AgentProfile] = []
        semaphore = __import__("asyncio").Semaphore(8)

        async def _build_profile(
            cluster_id: str, cluster_entities: list[EntityNode]
        ) -> AgentProfile | None:
            async with semaphore:
                # Use the most relevant entity in the cluster as representative
                representative = max(cluster_entities, key=lambda e: e.relevance_score)
                agent_name = representative.name

                # Fetch full node properties
                nodes_map = await self._repo.fetch_nodes_by_names([agent_name])
                node = nodes_map.get(agent_name) or {
                    "name": agent_name,
                    **representative.properties,
                }

                # Calculate metrics using repo method
                # For cluster-based synthesis, we construct synthetic sector_results
                sector_results = self._build_sector_results_from_cluster(cluster_entities)

                max_relevance = max(
                    e.relevance_score for e in cluster_entities
                ) if cluster_entities else 1.0

                metrics = await self._repo._calculate_agent_metrics_and_context_for_llm(
                    agent_name=agent_name,
                    node=node,
                    sector_results=sector_results,
                    max_relevance=max_relevance,
                )

                # Build profile
                return await self._repo._build_single_agent_profile_from_node(
                    agent_name=agent_name,
                    node=node,
                    user_query=query,
                    dataset_id=dataset_id,
                    agent_metrics=metrics,
                    sector_results=sector_results,
                    llm_output=None,
                )

        # Process clusters in parallel
        tasks = [
            _build_profile(cluster_id, cluster_entities)
            for cluster_id, cluster_entities, _ in top_clusters
        ]
        results = await __import__("asyncio").gather(*tasks)
        profiles = [p for p in results if p is not None]

        return profiles

    def _build_sector_results_from_cluster(
        self, cluster_entities: list[EntityNode]
    ) -> list[dict[str, Any]]:
        """Build synthetic sector_results from a cluster of entities."""
        if not cluster_entities:
            return []

        # Use the top entity's domain tags as the sector
        primary = cluster_entities[0]
        domain_tag = primary.domain_tags[0] if primary.domain_tags else primary.label

        # Collect all unique agent names from cluster
        evidence_nodes = [e.name for e in cluster_entities if e.name]
        total_relevance = sum(e.relevance_score for e in cluster_entities)
        density = len(cluster_entities)

        return [
            {
                "domain_tag": domain_tag,
                "total_relevance": total_relevance,
                "evidence_nodes": evidence_nodes,
                "density": density,
            }
        ]
