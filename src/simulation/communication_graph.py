"""
Communication Graph: computes which agents communicate with which.
Entity overlap determines communication eligibility — no broadcast.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Set, Optional
from itertools import combinations

from src.simulation.agent_node import AgentNode
from src.simulation.debate_config import DebateConfig


@dataclass
class CommPair:
    """A communication pair between two agents."""
    agent_a: str  # agent ID
    agent_b: str  # agent ID
    shared_entities: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)


class CommunicationGraph:
    """
    Computes agent communication pairs based on entity overlap.

    Global constraint: Communication eligibility is computed from entity overlap,
    no broadcast — agents only communicate when they share relevant entities.
    """

    def compute_pairs(
        self,
        agents: List[AgentNode],
        threshold: int = 1,
    ) -> List[CommPair]:
        """
        Compute communication pairs from entity overlap.

        For each agent pair (A, B), compute overlap = A.domain_tags ∩ B.domain_tags.
        If len(overlap) >= threshold, create a communication link.

        Args:
            agents: List of AgentNode instances
            threshold: Minimum shared entities to form a link (default 1)

        Returns:
            List of CommPair instances
        """
        pairs: List[CommPair] = []

        for agent_a, agent_b in combinations(agents, 2):
            overlap = self._compute_overlap(agent_a, agent_b)
            if len(overlap) >= threshold:
                pair = CommPair(
                    agent_a=str(agent_a.id),
                    agent_b=str(agent_b.id),
                    shared_entities=list(overlap),
                    evidence=self._build_evidence(agent_a, agent_b, overlap),
                )
                pairs.append(pair)

        return pairs

    def get_round_pairs(
        self,
        agents: List[AgentNode],
        round_num: int,
        config: DebateConfig,
    ) -> List[CommPair]:
        """
        Get communication pairs for a specific debate round.

        Round 1: Direct neighbors only (pairs with overlap)
        Round 2+: Expand based on config.comm_radius

        Args:
            agents: List of AgentNode instances
            round_num: Current round number (1-indexed)
            config: DebateConfig with comm_radius and max_pairs_per_round

        Returns:
            List of CommPair instances for this round
        """
        # Round 1: direct neighbors only
        if round_num == 1:
            pairs = self.compute_pairs(agents, threshold=1)
        else:
            # Round 2+: expand with communication radius
            pairs = self.compute_pairs(agents, threshold=1)

            # Expand pairs based on comm_radius
            expanded = self._expand_by_radius(agents, pairs, config.comm_radius)
            pairs = self._deduplicate_pairs(expanded)

        # Cap to max pairs per round
        if len(pairs) > config.max_pairs_per_round:
            pairs = self._cap_pairs(pairs, config.max_pairs_per_round)

        return pairs

    def expand_with_referenced(
        self,
        agents: List[AgentNode],
        referenced_ids: List[str],
        agents_to_add: Optional[List[AgentNode]] = None,
    ) -> List[AgentNode]:
        """
        Add agents referenced in Round 1 responses.

        After Round 1, agents may reference other agents that weren't in the
        initial communication graph. This method expands the agent set to
        include those referenced agents.

        Args:
            agents: Current list of AgentNode instances
            referenced_ids: List of agent IDs referenced in responses
            agents_to_add: Optional list of AgentNode instances to add.
                           Caller should fetch these from repository based on referenced_ids.

        Returns:
            Expanded list of AgentNode instances (original + newly referenced)
        """
        if not referenced_ids:
            return agents

        existing_ids: Set[str] = {str(a.id) for a in agents}
        new_ids = [rid for rid in referenced_ids if rid not in existing_ids]

        if not new_ids or not agents_to_add:
            return agents

        # Filter agents_to_add to only include those in new_ids
        new_agents = [a for a in agents_to_add if str(a.id) in new_ids]

        return agents + new_agents

    def _compute_overlap(self, agent_a: AgentNode, agent_b: AgentNode) -> Set[str]:
        """Compute shared entity tags between two agents."""
        tags_a = set(agent_a.domain_tags)
        tags_b = set(agent_b.domain_tags)
        return tags_a & tags_b

    def _build_evidence(
        self,
        agent_a: AgentNode,
        agent_b: AgentNode,
        overlap: Set[str],
    ) -> List[str]:
        """Build evidence/explanation for why these agents communicate."""
        evidence = [
            f"{agent_a.name} and {agent_b.name} share domain tags: {', '.join(sorted(overlap))}",
        ]
        # Add entity affinity overlap if available
        affinity_a = set(agent_a.entity_affinity)
        affinity_b = set(agent_b.entity_affinity)
        affinity_overlap = affinity_a & affinity_b
        if affinity_overlap:
            evidence.append(
                f"Both connect to entity types: {', '.join(sorted(affinity_overlap))}"
            )
        return evidence

    def _expand_by_radius(
        self,
        agents: List[AgentNode],
        pairs: List[CommPair],
        radius: int,
    ) -> List[CommPair]:
        """
        Expand pairs based on communication radius.

        For radius > 1, find agents that connect to existing pairs and
        create indirect communication links.
        """
        if radius <= 1:
            return pairs

        # Build adjacency map from existing pairs
        adjacency: dict[str, Set[str]] = {}
        for pair in pairs:
            adjacency.setdefault(pair.agent_a, set()).add(pair.agent_b)
            adjacency.setdefault(pair.agent_b, set()).add(pair.agent_a)

        # For each agent, find agents within radius hops
        expanded_pairs: List[CommPair] = list(pairs)

        for agent in agents:
            agent_id = str(agent.id)
            if agent_id not in adjacency:
                continue

            # BFS to find agents within radius
            visited: Set[str] = {agent_id}
            frontier: Set[str] = adjacency.get(agent_id, set())
            current_radius = 1

            while frontier and current_radius < radius:
                next_frontier: Set[str] = set()
                for neighbor_id in frontier:
                    if neighbor_id not in visited:
                        visited.add(neighbor_id)
                        next_frontier |= adjacency.get(neighbor_id, set())
                frontier = next_frontier
                current_radius += 1

            # Create pairs with agents within radius
            for other_id in visited:
                if other_id == agent_id:
                    continue
                # Check if pair already exists
                existing = any(
                    (p.agent_a == agent_id and p.agent_b == other_id) or
                    (p.agent_a == other_id and p.agent_b == agent_id)
                    for p in expanded_pairs
                )
                if not existing:
                    # Find shared entities for new pair
                    other_agent = next(
                        (a for a in agents if str(a.id) == other_id), None
                    )
                    if other_agent:
                        overlap = self._compute_overlap(agent, other_agent)
                        if overlap:
                            new_pair = CommPair(
                                agent_a=agent_id,
                                agent_b=other_id,
                                shared_entities=list(overlap),
                                evidence=[f"Within {radius}-hop radius"],
                            )
                            expanded_pairs.append(new_pair)

        return expanded_pairs

    def _deduplicate_pairs(self, pairs: List[CommPair]) -> List[CommPair]:
        """Remove duplicate pairs (A,B) == (B,A)."""
        seen: Set[tuple[str, str]] = set()
        unique: List[CommPair] = []

        for pair in pairs:
            canonical = tuple(sorted([pair.agent_a, pair.agent_b]))
            if canonical not in seen:
                seen.add(canonical)
                unique.append(pair)

        return unique

    def _cap_pairs(
        self,
        pairs: List[CommPair],
        max_pairs: int,
    ) -> List[CommPair]:
        """Cap pairs to maximum, prioritizing by overlap size."""
        # Sort by number of shared entities (descending)
        sorted_pairs = sorted(
            pairs,
            key=lambda p: len(p.shared_entities),
            reverse=True,
        )
        return sorted_pairs[:max_pairs]
