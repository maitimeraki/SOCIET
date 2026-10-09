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

# Step 9: bound what the summary prompt may carry from the transcript.
SUMMARY_TRANSCRIPT_MAX_TURNS = 20
SUMMARY_TRANSCRIPT_MAX_CHARS = 8000

# Step 7: a dominant share below this is a near-tie, not a mandate.
CONTESTED_THRESHOLD = 0.6


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
            llm_summary = await self._allm_summary(llm_client, verdict, rounds)
            if llm_summary:
                verdict.summary = llm_summary
        return verdict

    async def _allm_summary(
        self,
        llm_client: "LLMClient",
        verdict: DebateVerdict,
        rounds: list[RoundResult],
    ) -> str | None:
        """Async LLM summary -- no asyncio.run, no loop collision.

        The prompt carries the bounded debate transcript, not just the
        aggregates, so the summary is a synthesis of the argument rather than
        a restatement of the turn count.
        """
        transcript, turns_used = self._render_transcript(rounds)
        contested_note = " (contested near-tie)" if verdict.contested else ""
        system_prompt = (
            "You are a neutral debate summarizer. Write a concise verdict "
            "summary grounded ONLY in the debate transcript below. Reference "
            "the actual arguments, not the turn counts. Keep it under 600 chars."
        )
        user_prompt = (
            f"Overall stance: {verdict.overall_stance.value}\n"
            f"Dominant share of weight: {verdict.weight_share:.2f}{contested_note}\n"
            f"Top supporting entities: {verdict.supporting_entities[:5]}\n"
            f"Top opposing entities: {verdict.opposing_entities[:5]}\n\n"
            f"Debate transcript (last {turns_used} turns):\n{transcript}"
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

    @staticmethod
    def _render_transcript(rounds: list[RoundResult]) -> tuple[str, int]:
        """Bounded transcript for the summary prompt: the last-N turns within a
        total char cap, newest-first so the most recent argument is never the
        one dropped. Returns (text, turns_included)."""
        turns = [turn for round_result in rounds for turn in round_result.turns]
        lines: list[str] = []
        budget = SUMMARY_TRANSCRIPT_MAX_CHARS
        for turn in reversed(turns[-SUMMARY_TRANSCRIPT_MAX_TURNS:]):
            line = f"[{turn.stance}] {turn.agent_name}: {turn.content}"
            if len(line) > budget:
                break
            lines.append(line)
            budget -= len(line)
        lines.reverse()
        return "\n".join(lines), len(lines)

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
                weight_share=0.0,
                contested=False,
            )

        clusters = self._cluster_opinions(all_turns)
        profile_map = {p.identity.name: p for p in profiles}

        warned_missing: set[str] = set()
        weights = self._calibrate_cior(clusters, profile_map, warned=warned_missing)

        cluster_details: dict[Stance, ClusterSummary] = {}
        for stance, turns in clusters.items():
            if not turns:
                continue
            avg_conf = sum(t.confidence for t in turns) / len(turns)
            total_weight = weights.get(stance, 0.0)

            convictions: List[float] = []
            for turn in turns:
                profile = profile_map.get(turn.agent_name)
                if profile is None:
                    self._warn_missing_profile(turn.agent_name, warned_missing)
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
        weight_share = max_weight / total_weight_sum if total_weight_sum > 0 else 0.0
        # `confidence_score` keeps its long-standing number; `weight_share` is
        # the same value under its honest name. `contested` stops a near-tie
        # from reading as a mandate.
        confidence_score = weight_share
        contested = weight_share < CONTESTED_THRESHOLD

        supporting: list[str] = []
        opposing: list[str] = []
        provenance_by_claim: dict[str, list] = {}
        for turn in all_turns:
            try:
                turn_stance = Stance(turn.stance) if isinstance(turn.stance, str) else turn.stance
            except ValueError:
                turn_stance = Stance.NEUTRAL
            if turn_stance == overall_stance:
                supporting.extend(turn.references)
            else:
                opposing.extend(turn.references)
            # Trace each claim back to provenance reachable from its speaker;
            # never fabricate — a turn with no references contributes nothing.
            profile = profile_map.get(turn.agent_name)
            if profile is not None:
                for ref in turn.references:
                    links = provenance_by_claim.setdefault(ref, [])
                    for link in profile.summary_provenance:
                        if link not in links:
                            links.append(link)

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
            provenance_by_claim=provenance_by_claim,
            rounds_executed=len(rounds),
            weight_share=weight_share,
            contested=contested,
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

    @staticmethod
    def _warn_missing_profile(agent_name: str, warned: set[str]) -> None:
        """One warning per agent per synthesis: the speaker is absent from profile_map."""
        if agent_name in warned:
            return
        warned.add(agent_name)
        logger.warning(
            "VerdictSynthesizer: agent '%s' absent from profile_map; "
            "falling back to conviction=0.5, cior=0.0 (reduced weight)",
            agent_name,
        )

    def _calibrate_cior(
        self,
        clusters: dict[Stance, list[AgentTurn]],
        profile_map: dict[str, Agent],
        warned: set[str] | None = None,
    ) -> dict[Stance, float]:
        """weight = confidence * conviction * cior_factor.

        cior_factor maps cior in [-1, 1] into [0.5, 1.0]:
            cior_factor = 0.5 + (cior + 1) / 4
        Receptivity scales a voice's emphasis; it never erases one. A hostile
        dissenter (cior = -1) keeps half weight instead of dropping to zero.
        """
        warned = set() if warned is None else warned
        weights: dict[Stance, float] = {s: 0.0 for s in Stance}
        for stance, turns in clusters.items():
            cluster_weight = 0.0
            for turn in turns:
                profile = profile_map.get(turn.agent_name)
                if profile is not None:
                    cior_factor = 0.5 + (profile.cior + 1.0) / 4.0
                    cluster_weight += turn.confidence * profile.conviction * cior_factor
                else:
                    self._warn_missing_profile(turn.agent_name, warned)
                    cluster_weight += turn.confidence * 0.5
            weights[stance] = cluster_weight
        return weights
