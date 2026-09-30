"""
Agent Spawner: Converts graph entities to canonical Agent personas.

All BCO (Belief-Conviction-Opinion) and CIOR metrics are derived from
entity data. Output is the canonical `Agent` model -- the legacy
`AgentNode` shim is left in place for callers that still expect it.
"""
from __future__ import annotations

from typing import List, Optional, Any

from src.persona.agent import (
    Agent,
    ConfidenceBreakdown,
    DiscoveryType,
    ExpertiseLevel,
    GraphSnapshot,
    PersonaIdentity,
    ProvenanceLink,
    Stance,
)
from src.persona.graph_context import GraphContext, EntityNode


_ENTITY_STANCE_MAP = {
    "competitor": Stance.NEGATIVE,
    "partner": Stance.POSITIVE,
    "regulator": Stance.NEUTRAL,
    "customer": Stance.POSITIVE,
    "supplier": Stance.NEUTRAL,
}

_DEFAULT_STANCE = Stance.NEUTRAL

_RISK_AVERSE_TYPES = {"regulator", "compliance", "auditor", "risk_management"}
_GROWTH_ORIENTED_TYPES = {"startup", "investor", "partner", "customer", "vendor"}


class AgentSpawner:
    """Spawns canonical `Agent` instances from graph entities."""

    def __init__(self, graph_context: Optional[GraphContext] = None):
        self._graph = graph_context

    @property
    def graph(self) -> GraphContext:
        if self._graph is None:
            raise RuntimeError(
                "AgentSpawner requires a GraphContext. Initialize with graph_context parameter."
            )
        return self._graph

    async def spawn_agents_from_query(
        self,
        query: str,
        max_agents: int = 8,
    ) -> List[Agent]:
        entities = await self.graph.find_relevant_entities(query, limit=max_agents)
        agents = [self._spawn_agent(entity) for entity in entities]
        return agents[:max_agents]

    def _spawn_agent(self, entity: EntityNode) -> Agent:
        stance = self._derive_stance(entity)
        intensity = self._derive_intensity(entity)
        confidence = self._derive_confidence(entity)
        belief = self._derive_belief(entity)
        cior = self._derive_cior(entity)
        instinct_tags = self._derive_instinct_tags(entity)
        domain_tags = self._derive_domain_tags(entity)
        entity_affinity = self._derive_entity_affinity(entity)
        role_description = entity.summary or f"{entity.name} - {entity.label}"

        # BCO/CIOR-derived fields are surfaced as Agent fields directly.
        # Provenance + confidence breakdown are populated lazily on first debate.
        return Agent(
            identity=PersonaIdentity(
                name=entity.name,
                archetype=entity.label,
                communication_style="data-driven",
            ),
            discovery_type=DiscoveryType.GRAPH_DISCOVERY,
            expertise_level=ExpertiseLevel.STRATEGIC,
            bio=f"{entity.name} - {entity.label}",
            detailed_perspective=belief,
            role_description=role_description,
            stance=stance,
            intensity=intensity,
            confidence=confidence,
            conviction=self._derive_conviction(entity, confidence),
            belief=belief,
            opinion="",
            cior=cior,
            instinct_tags=instinct_tags,
            domain_tags=domain_tags,
            entity_affinity=entity_affinity,
            expertise_areas=domain_tags[:3],
            communication_radius=1,
            summary_provenance=[],
            confidence_breakdown=ConfidenceBreakdown(
                source_breadth=0,
                node_density=int(entity.properties.get("connection_count", 0)) or 1,
                relationship_connectivity=float(entity.properties.get("centrality_score", 0.5)) or 0.5,
            ),
            graph_snapshot=GraphSnapshot(dataset_id="unknown"),
        )

    def _derive_stance(self, entity: EntityNode) -> Stance:
        """
        Derive agent stance from entity type/label.

        Rules:
        - Competitor NEGATIVE
        - Partner POSITIVE
        - Regulator NEUTRAL
        - Customer POSITIVE
        - Supplier NEUTRAL

        Args:
            entity: The graph entity.

        Returns:
            The derived Stance value.
        """
        label_lower = entity.label.lower()
        return _ENTITY_STANCE_MAP.get(label_lower, _DEFAULT_STANCE)

    def _derive_intensity(self, entity: EntityNode) -> float:
        """
        Derive response intensity from entity properties and relevance.

        Range: 0.0 to 1.0
        Based on relevance_score (higher = more intense).

        Args:
            entity: The graph entity.

        Returns:
            Intensity value in [0.0, 1.0].
        """
        base = 0.5
        relevance = entity.relevance_score

        # Boost intensity for highly relevant entities
        if relevance > 0.8:
            intensity = min(1.0, base + 0.3)
        elif relevance > 0.6:
            intensity = min(1.0, base + 0.15)
        elif relevance < 0.3:
            intensity = max(0.0, base - 0.15)
        else:
            intensity = base

        # Allow property override
        prop_intensity = entity.properties.get("intensity")
        if prop_intensity is not None:
            try:
                intensity = float(prop_intensity)
            except (TypeError, ValueError):
                pass

        return intensity

    def _derive_confidence(self, entity: EntityNode) -> float:
        """
        Derive confidence from graph connectivity metrics.

        Range: 0.0 to 1.0

        Args:
            entity: The graph entity.

        Returns:
            Confidence value in [0.0, 1.0].
        """
        # Start with relevance as base
        confidence = entity.relevance_score

        # Boost for entities with rich properties
        if entity.summary:
            confidence = min(1.0, confidence + 0.1)

        # Boost for entities with domain tags
        if entity.domain_tags:
            confidence = min(1.0, confidence + 0.05 * min(len(entity.domain_tags), 3))

        # Allow property override for explicit confidence
        prop_confidence = entity.properties.get("confidence")
        if prop_confidence is not None:
            try:
                confidence = float(prop_confidence)
            except (TypeError, ValueError):
                pass

        # Ensure bounds
        return max(0.0, min(1.0, confidence))

    def _derive_belief(self, entity: EntityNode) -> str:
        """
        Derive agent belief/world model from entity summary and properties.

        Args:
            entity: The graph entity.

        Returns:
            A belief string representing the agent worldview.
        """
        # Priority: explicit belief prop > summary > archetype-based
        belief = entity.properties.get("belief", "")
        if belief:
            return str(belief)

        if entity.summary:
            # Truncate and use summary as belief foundation
            return entity.summary[:500]

        # Fallback to archetype-based belief
        archetype_beliefs = {
            "competitor": "Competition drives excellence and innovation through market pressure.",
            "partner": "Collaboration and mutual benefit create sustainable value.",
            "regulator": "Rules and oversight protect stakeholders and maintain order.",
            "customer": "Customer needs and satisfaction are paramount to success.",
            "supplier": "Reliable supply chains and quality materials are essential foundations.",
        }
        label_lower = entity.label.lower()
        return archetype_beliefs.get(label_lower, f"I am {entity.name} and I represent the {entity.label} perspective.")

    def _derive_cior(self, entity: EntityNode) -> float:
        """
        Derive CIOR (Certainty-Instinct Opinion Range) from entity type.

        Range: -1.0 to 1.0
        - Negative: risk-averse (regulators, auditors)
        - Positive: growth-oriented (partners, customers, startups)

        Args:
            entity: The graph entity.

        Returns:
            CIOR value in [-1.0, 1.0].
        """
        label_lower = entity.label.lower()

        # Check explicit property first
        prop_cior = entity.properties.get("cior")
        if prop_cior is not None:
            try:
                return max(-1.0, min(1.0, float(prop_cior)))
            except (TypeError, ValueError):
                pass

        # Risk-averse entities get negative CIOR
        if label_lower in _RISK_AVERSE_TYPES:
            return -0.5

        # Growth-oriented entities get positive CIOR
        if label_lower in _GROWTH_ORIENTED_TYPES:
            return 0.5

        # Default to slightly positive (balanced)
        return 0.1

    def _derive_instinct_tags(self, entity: EntityNode) -> List[str]:
        """
        Derive behavioral instinct tags from entity properties and type.

        Args:
            entity: The graph entity.

        Returns:
            List of instinct tag strings.
        """
        tags: List[str] = []

        # From explicit property
        prop_tags = entity.properties.get("instinct_tags")
        if prop_tags:
            if isinstance(prop_tags, list):
                tags.extend(str(t) for t in prop_tags)
            elif isinstance(prop_tags, str):
                tags.extend(t.strip() for t in prop_tags.split(",") if t.strip())

        # Derive from entity type
        label_lower = entity.label.lower()
        if label_lower in _RISK_AVERSE_TYPES:
            tags.append("risk_averse")
        if label_lower in _GROWTH_ORIENTED_TYPES:
            tags.append("growth_seeker")

        # Derive from properties
        if entity.properties.get("cautious") or entity.properties.get("conservative"):
            tags.append("cautious")

        if entity.properties.get("aggressive") or entity.properties.get("ambitious"):
            tags.append("assertive")

        if entity.properties.get("collaborative"):
            tags.append("collaborative")

        # Remove duplicates while preserving order
        seen = set()
        unique_tags = []
        for tag in tags:
            if tag not in seen:
                seen.add(tag)
                unique_tags.append(tag)

        return unique_tags

    def _derive_domain_tags(self, entity: EntityNode) -> List[str]:
        """
        Derive domain tags from entity domain_tags and properties.

        Args:
            entity: The graph entity.

        Returns:
            List of domain tag strings.
        """
        tags: List[str] = []

        # Use entity's domain_tags first
        tags.extend(entity.domain_tags)

        # Fall back to property-based tags
        prop_tags = entity.properties.get("domain_tags")
        if prop_tags:
            if isinstance(prop_tags, list):
                tags.extend(str(t) for t in prop_tags)
            elif isinstance(prop_tags, str):
                tags.extend(t.strip() for t in prop_tags.split(",") if t.strip())

        # Also check expertise_areas and tags
        for key in ("expertise_areas", "tags", "expertise"):
            val = entity.properties.get(key)
            if val:
                if isinstance(val, list):
                    tags.extend(str(t) for t in val)
                elif isinstance(val, str):
                    tags.extend(t.strip() for t in val.split(",") if t.strip())

        # Remove duplicates while preserving order
        seen = set()
        unique_tags = []
        for tag in tags:
            tag_normalized = tag.lower().strip()
            if tag_normalized and tag_normalized not in seen:
                seen.add(tag_normalized)
                unique_tags.append(tag.strip())

        return unique_tags

    def _derive_entity_affinity(self, entity: EntityNode) -> List[str]:
        """
        Derive entity affinity (which entity types this agent connects to).

        Args:
            entity: The graph entity.

        Returns:
            List of entity type strings this agent prefers to engage with.
        """
        # Default affinities based on entity type
        label_lower = entity.label.lower()

        affinity_map = {
            "competitor": ["competitor", "partner", "customer"],
            "partner": ["partner", "customer", "supplier"],
            "regulator": ["competitor", "partner", "customer", "supplier"],
            "customer": ["supplier", "partner"],
            "supplier": ["customer", "partner"],
        }

        return affinity_map.get(label_lower, ["partner", "customer"])

    def _derive_conviction(self, entity: EntityNode, confidence: float) -> float:
        """
        Derive conviction (how unshakeable the belief is) from confidence.

        Conviction is derived from confidence but slightly amplified
        since conviction represents commitment to belief.

        Args:
            entity: The graph entity.
            confidence: The derived confidence value.

        Returns:
            Conviction value in [0.0, 1.0].
        """
        # Conviction is belief firmness - typically higher than raw confidence
        conviction = min(1.0, confidence * 1.1)

        # Allow property override
        prop_conviction = entity.properties.get("conviction")
        if prop_conviction is not None:
            try:
                conviction = float(prop_conviction)
            except (TypeError, ValueError):
                pass

        return conviction


# ---- CLI Test ----

if __name__ == "__main__":
    import asyncio

    async def test():
        from src.persona.graph_context import GraphContext

        async with GraphContext() as ctx:
            spawner = AgentSpawner(graph_context=ctx)
            agents = await spawner.spawn_agents_from_query(
                "AI ethics healthcare",
                max_agents=5,
            )
            print(f"Spawned {len(agents)} agents:")
            for agent in agents:
                print(f"  - {agent.name} ({agent.archetype}): stance={agent.stance}, cior={agent.cior:.2f}")

    asyncio.run(test())
