"""VerdictSynthesizer: cluster-weighted CIOR synthesis for debate verdicts."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List

from src.persona.agent import Agent, Stance
from src.simulation.pair_turn import (
    AgentTurn,
    ClusterSummary,
    DebateVerdict,
    RoundResult,
)

if TYPE_CHECKING:
    from src.llm.client import LLMClient

logger = logging.getLogger(__name__)

SUMMARY_MAX_CHARS = 600


class VerdictSynthesizer:
    """Cluster-weighted CIOR synthesizer.

    Reads `conviction` and `cior` directly from the canonical `Agent`
    (not from the legacy `AgentProfile` -- see Gap P1).
    """

    async def asynthesize(
        self,
        rounds: list[RoundResult],
        profiles: list[Agent],
        llm_client: "LLMClient | None" = None,
    ) -> DebateVerdict:
        """Async synthesis -- safe to call from any running event loop."""
        verdict = self.synthesize(rounds=rounds, profiles=profiles, llm_client=None)
        if llm_client is not None:
            llm_summary = await self._allm_summary(llm_client, verdict)
            if llm_summary:
                verdict.summary = llm_summary
        return verdict

    async def _allm_summary(
        self,
        llm_client: "LLMClient",
        verdict: DebateVerdict,
    ) -> str | None:
        """Async LLM summary -- no asyncio.run, no loop collision."""
        system_prompt = (
            "You are a neutral debate summarizer. Produce a concise verdict "
            "summary from the aggregate statistics below. Keep it under 600 chars."
        )
        user_prompt = (
            f"Overall stance: {verdict.overall_stance.value}\n"
            f"Confidence score: {verdict.confidence_score:.2f}\n"
            f"Top supporting entities: {verdict.supporting_entities[:5]}\n"
            f"Top opposing entities: {verdict.opposing_entities[:5]}"
        )
        try:
            raw = await llm_client.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.3,
            )
        except Exception:
            logger.exception("LLM summary generation failed; using template")
            return None
        if not raw:
            return None
        return raw.strip()[:SUMMARY_MAX_CHARS]

    def synthesize(
        self,
        rounds: list[RoundResult],
        profiles: list[Agent],
        llm_client: "LLMClient | None" = None,
    ) -> DebateVerdict:
        all_turns: list[AgentTurn] = []
        for round_result in rounds:
            all_turns.extend(round_result.turns)

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

        clusters = self._cluster_opinions(all_turns)
        profile_map = {p.identity.name: p for p in profiles}

        weights = self._calibrate_cior(clusters, profile_map)

        cluster_details: dict[Stance, ClusterSummary] = {}
        for stance, turns in clusters.items():
            if not turns:
                continue
            avg_conf = sum(t.confidence for t in turns) / len(turns)
            total_weight = weights.get(stance, 0.0)

            convictions: List[float] = []
            for turn in turns:
                profile = profile_map.get(turn.agent_name)
                convictions.append(profile.conviction if profile else 0.5)
            avg_conv = sum(convictions) / len(convictions) if convictions else 0.5

            cluster_details[stance] = ClusterSummary(
                stance=stance,
                count=len(turns),
                total_weight=total_weight,
                avg_confidence=avg_conf,
                avg_conviction=avg_conv,
                agents=[t.agent_name for t in turns],
            )

        overall_stance = Stance.NEUTRAL
        max_weight = 0.0
        for stance, weight in weights.items():
            if weight > max_weight:
                max_weight = weight
                overall_stance = stance

        total_weight_sum = sum(weights.values())
        confidence_score = max_weight / total_weight_sum if total_weight_sum > 0 else 0.0

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

        dominant_count = cluster_details.get(
            overall_stance,
            ClusterSummary(
                stance=overall_stance, count=0, total_weight=0.0,
                avg_confidence=0.0, avg_conviction=0.0, agents=[],
            ),
        ).count
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
        profile_map: dict[str, Agent],
    ) -> dict[Stance, float]:
        """weight = confidence * conviction * (1 + cior) / 2."""
        weights: dict[Stance, float] = {s: 0.0 for s in Stance}
        for stance, turns in clusters.items():
            cluster_weight = 0.0
            for turn in turns:
                profile = profile_map.get(turn.agent_name)
                if profile is not None:
                    cior_factor = (1.0 + profile.cior) / 2.0
                    cluster_weight += turn.confidence * profile.conviction * cior_factor
                else:
                    cluster_weight += turn.confidence * 0.5
            weights[stance] = cluster_weight
        return weights
