"""VerdictSynthesizer: cluster-weighted CIOR synthesis for debate verdicts."""
from __future__ import annotations

from typing import TYPE_CHECKING
from src.simulation.pair_turn import (
    RoundResult,
    DebateVerdict,
    ClusterSummary,
    AgentTurn,
)
from src.simulation.agent_node import Stance

if TYPE_CHECKING:
    from src.llm.client import LLMClient


class VerdictSynthesizer:
    """Pure function synthesizer — no constructor needed."""

    def synthesize(
        self,
        rounds: list[RoundResult],
        profiles: list,
        llm_client: "LLMClient | None" = None,
    ) -> DebateVerdict:
        """
        Synthesize a DebateVerdict from debate rounds and agent profiles.

        Steps:
          1. Collect all turns from all rounds.
          2. Cluster by stance.
          3. Weight by confidence × conviction × CIOR factor.
          4. Determine overall stance (max weight cluster).
          5. Confidence = max_weight / total_weight.
          6. Collect supporting/opposing entities from turn references.
          7. Generate summary via LLM or template fallback.
        """
        # Step 1: Collect all turns
        all_turns: list[AgentTurn] = []
        for round_result in rounds:
            all_turns.extend(round_result.turns)

        # Edge: no rounds or no turns
        if not all_turns:
            return DebateVerdict(
                overall_stance=Stance.NEUTRAL,
                confidence_score=0.0,
                supporting_entities=[],
                opposing_entities=[],
                summary="No debate occurred.",
                cluster_details={},
                rounds_executed=len(rounds),
            )

        # Step 2: Cluster opinions
        clusters = self._cluster_opinions(all_turns)

        # Build profile map (by agent_name, matching the brief)
        profile_map = {p.identity.name: p for p in profiles}

        # Step 3: CIOR-calibrated weights
        weights = self._calibrate_cior(clusters, profile_map)

        # Build cluster summaries with weights
        cluster_details: dict[Stance, ClusterSummary] = {}
        for stance, turns in clusters.items():
            if not turns:
                continue
            avg_conf = sum(t.confidence for t in turns) / len(turns)
            total_weight = weights.get(stance, 0.0)

            # avg conviction from profiles
            convictions = []
            for turn in turns:
                profile = profile_map.get(turn.agent_name)
                conviction = getattr(profile, "conviction", 0.5) if profile else 0.5
                convictions.append(conviction)
            avg_conv = sum(convictions) / len(convictions) if convictions else 0.5

            cluster_details[stance] = ClusterSummary(
                stance=stance,
                count=len(turns),
                total_weight=total_weight,
                avg_confidence=avg_conf,
                avg_conviction=avg_conv,
                agents=[t.agent_name for t in turns],
            )

        # Step 4: Overall stance = max weight cluster
        overall_stance = Stance.NEUTRAL
        max_weight = 0.0
        for stance, weight in weights.items():
            if weight > max_weight:
                max_weight = weight
                overall_stance = stance

        # Step 5: Confidence score
        total_weight_sum = sum(weights.values())
        confidence_score = max_weight / total_weight_sum if total_weight_sum > 0 else 0.0

        # Step 6: Collect supporting/opposing entities
        supporting: list[str] = []
        opposing: list[str] = []
        for turn in all_turns:
            try:
                turn_stance = Stance(turn.stance) if isinstance(turn.stance, str) else turn.stance
            except ValueError:
                turn_stance = Stance.NEUTRAL
            if turn_stance == overall_stance:
                supporting.extend(turn.references)
            else:
                opposing.extend(turn.references)

        # Step 7: Summary
        dominant_count = cluster_details.get(overall_stance, ClusterSummary(
            stance=overall_stance, count=0, total_weight=0.0,
            avg_confidence=0.0, avg_conviction=0.0, agents=[],
        )).count
        dominant_pct = (dominant_count / len(all_turns) * 100) if all_turns else 0

        summary = (
            f"The debate concluded with {dominant_pct:.0f}% of turns expressing "
            f"{overall_stance.value} stance. Confidence score: {confidence_score:.2f}."
        )

        return DebateVerdict(
            overall_stance=overall_stance,
            confidence_score=confidence_score,
            supporting_entities=list(set(supporting))[:10],
            opposing_entities=list(set(opposing))[:10],
            summary=summary,
            cluster_details=cluster_details,
            rounds_executed=len(rounds),
        )

    def _cluster_opinions(self, turns: list[AgentTurn]) -> dict[Stance, list[AgentTurn]]:
        """Group turns by stance."""
        clusters: dict[Stance, list[AgentTurn]] = {
            Stance.POSITIVE: [],
            Stance.NEGATIVE: [],
            Stance.NEUTRAL: [],
            Stance.AMBIVALENT: [],
        }
        for turn in turns:
            try:
                stance = Stance(turn.stance) if isinstance(turn.stance, str) else turn.stance
            except ValueError:
                stance = Stance.NEUTRAL
            clusters[stance].append(turn)
        return clusters

    def _calibrate_cior(
        self,
        clusters: dict[Stance, list[AgentTurn]],
        profile_map: dict,
    ) -> dict[Stance, float]:
        """
        Apply CIOR adjustment to cluster weights.

        Formula: weight = confidence × conviction × (1 + cior) / 2

        Falls back to conviction=0.5, cior=0.0 when profile or field missing.
        """
        weights: dict[Stance, float] = {s: 0.0 for s in Stance}
        for stance, turns in clusters.items():
            cluster_weight = 0.0
            for turn in turns:
                profile = profile_map.get(turn.agent_name)
                if profile:
                    conviction = getattr(profile, "conviction", 0.5)
                    cior = getattr(profile, "cior", 0.0)
                    cior_factor = (1 + cior) / 2
                    cluster_weight += turn.confidence * conviction * cior_factor
                else:
                    # Unrecognized agent: weight by confidence alone
                    cluster_weight += turn.confidence * 0.5
            weights[stance] = cluster_weight
        return weights
