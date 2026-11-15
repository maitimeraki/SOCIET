"""VerdictSynthesizer: consensus-weighted synthesis for debate verdicts."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel

from src.llm.config_llm import get_llm_config
from src.persona.agent import WIRE_STANCES, Agent, Stance
from src.persona.models_persona import ProvenanceLink
from src.simulation.evidence import EvidenceItem
from src.simulation.pair_turn import (
    AgentTurn,
    ClusterSummary,
    DebateVerdict,
    RoundResult,
)
from src.simulation.turn_protocol import (
    consensus_window,
    stance_weights,
    weighted_share,
)
from src.utils.json_extract import extract_json_object

if TYPE_CHECKING:
    from src.llm.client import LLMClient

logger = logging.getLogger(__name__)


def wire_stance(value: object) -> Stance | None:
    """A turn's stance on the wire, or None when it names no wire stance.

    None means the turn has no stance this turn: it is counted nowhere, and it
    is never filed under NEUTRAL.
    """
    try:
        stance = Stance.parse(value)
    except ValueError:
        return None
    return stance if stance in WIRE_STANCES else None


def cluster_by_stance(turns: Iterable[AgentTurn]) -> dict[Stance, list[AgentTurn]]:
    clusters: dict[Stance, list[AgentTurn]] = {s: [] for s in WIRE_STANCES}
    for turn in turns:
        stance = wire_stance(turn.stance)
        if stance is not None:
            clusters[stance].append(turn)
    return clusters


#: The summary of a debate with no consensus: no turn took a position (none spoke, or all abstained).
NO_VERDICT_SUMMARY = "No verdict: no agent took a position."

# Step 9: bound the transcript the answer-writer prompt may carry. Bound the
# input, never the answer — there is no character cap on the narrative itself.
SUMMARY_TRANSCRIPT_MAX_TURNS = 40
SUMMARY_TRANSCRIPT_MAX_CHARS = 16000

# Step 7: a dominant share below this is a near-tie, not a mandate.
CONTESTED_THRESHOLD = 0.6

# Bounded latency budget for the answer-writer: the first call plus two
# retries, each asking more strictly for bare JSON. After this the narrative
# falls back to `summary` — flagged on the verdict, never silent. The model and
# token budget come from LLMConfig (verdict_model / verdict_max_tokens).
VERDICT_MAX_ATTEMPTS = 3

# Appended to the prompt on retries: the previous reply was not valid JSON, so
# the format constraint is restated explicitly.
VERDICT_JSON_REINFORCEMENT = (
    "\n\nYour previous reply was not valid JSON. Reply with ONLY the JSON "
    "object — no markdown fences, no prose before or after it."
)

VERDICT_SYSTEM = (
    "You are the analyst who answers the user's question from the debate below. "
    "Reply with ONLY a JSON object, no prose, with keys: answer, reasoning, "
    "constraints_and_risks, dissenting_views (list of {stance, view}), "
    "evidence (list of {entity, claim}), confidence. Ground every claim in the "
    "transcript and the cited entities; do not invent facts."
)


class Verdict(BaseModel):
    """Structured analyst answer, validated at the boundary (spec §8.1, §8.6)."""

    answer: str
    reasoning: str
    constraints_and_risks: str
    dissenting_views: list[dict] = []
    evidence: list[dict] = []
    confidence: float = 0.0


def _parse_verdict(raw: str) -> Verdict | None:
    """Repair-then-validate: extract the JSON object, then validate it. None
    when there is no parseable object or the answer came back empty."""
    candidate = extract_json_object(raw)
    if candidate is None:
        return None
    try:
        parsed = Verdict.model_validate_json(candidate)
    except Exception:
        return None
    return parsed if parsed.answer.strip() else None


def _to_markdown(v: Verdict) -> str:
    """Assemble the narrative markdown from the structured verdict fields."""
    parts = [
        f"## Recommendation\n{v.answer}",
        f"## Reasoning\n{v.reasoning}",
    ]
    if v.constraints_and_risks:
        parts.append(f"## Constraints & Risks\n{v.constraints_and_risks}")
    # Dissent is rendered by the frontend as a structured list (plan T6), not
    # prose here — emitting it in markdown too showed it twice.
    parts.append(f"## Confidence\n{v.confidence:.2f}")
    return "\n\n".join(parts)


def _provenance_link(item: EvidenceItem) -> ProvenanceLink | None:
    """A real source link for one evidence item; None when its chunk id is not a UUID."""
    try:
        chunk_id = UUID(item.chunk_id)
    except ValueError:
        return None
    return ProvenanceLink(
        doc_id=item.doc_id, title=item.doc_title, breadcrumb=item.section, chunk_id=chunk_id
    )


class VerdictSynthesizer:
    """Consensus-weighted synthesizer.

    Reads `strength` and `confidence` directly from the canonical `Agent`.
    """

    async def asynthesize(
        self,
        rounds: list[RoundResult],
        profiles: list[Agent],
        llm_client: "LLMClient | None" = None,
        query: str = "",
        scenario: str = "",
        run_id: str = "",
    ) -> DebateVerdict:
        """Async synthesis -- safe to call from any running event loop.

        Always produces the deterministic template verdict; when a client is
        given it additionally writes the query-grounded answer into
        `narrative` (assembled from the structured `Verdict`). When the
        answer-writer cannot produce parseable JSON after bounded retries + a
        repair pass — or no client was given — the narrative degrades to
        `summary` and `narrative_status` is set to `"fallback"` (flagged, and
        logged with the run/query, never silent).
        """
        verdict = self.synthesize(rounds=rounds, profiles=profiles, llm_client=None)
        parsed = None
        if llm_client is not None:
            parsed = await self._allm_verdict(
                llm_client, verdict, rounds, query, scenario
            )
        if parsed is not None:
            verdict.dissenting_views = parsed.dissenting_views
            verdict.evidence = parsed.evidence
            verdict.narrative = _to_markdown(parsed)
            return verdict
        verdict.narrative = verdict.summary
        verdict.narrative_status = "fallback"
        logger.warning(
            "verdict narrative degraded to the summary (run=%s, query=%r): %s",
            run_id or "(none)",
            query[:120],
            (
                "no LLM client given"
                if llm_client is None
                else "answer-writer produced no parseable JSON after retries"
            ),
        )
        return verdict

    async def _allm_verdict(
        self,
        llm_client: "LLMClient",
        verdict: DebateVerdict,
        rounds: list[RoundResult],
        query: str,
        scenario: str,
    ) -> Verdict | None:
        """Strict-JSON answer-writer -- no asyncio.run, no loop collision.

        The prompt carries the query and the bounded transcript, not just the
        aggregates, so the answer addresses the question from the argument.
        Bounded retries (VERDICT_MAX_ATTEMPTS total calls): each retry restates
        the bare-JSON constraint, and every reply goes through the repair pass in
        `_parse_verdict`. Returns None only once every attempt has failed, so the
        caller can flag the fallback.
        """
        transcript, turns_used = self._render_transcript(rounds)
        contested_note = " -- contested" if verdict.contested else ""
        user_prompt = (
            f"QUESTION: {query or '(none)'}\n"
            f"SCENARIO CONTEXT: {scenario or '(none)'}\n"
            f"Overall stance: {verdict.overall_stance.value} "
            f"(share {verdict.weight_share:.2f}{contested_note})\n"
            f"Supporting entities: {verdict.supporting_entities[:10]}\n"
            f"Opposing entities: {verdict.opposing_entities[:10]}\n\n"
            f"DEBATE TRANSCRIPT (last {turns_used} turns):\n{transcript}"
        )
        cfg = get_llm_config()
        from src.billing import metering

        for attempt in range(1, VERDICT_MAX_ATTEMPTS + 1):
            prompt = (
                user_prompt
                if attempt == 1
                else user_prompt + VERDICT_JSON_REINFORCEMENT
            )
            try:
                with metering.source_scope("verdict"):
                    raw = await llm_client.generate(
                        system_prompt=VERDICT_SYSTEM,
                        user_prompt=prompt,
                        temperature=0.4,
                        max_tokens=cfg.verdict_max_tokens,
                        model=cfg.verdict_model,
                    )
            except metering.MeteringError:
                # Accounting already failed: stop the job instead of retrying
                # into a deterministic fallback verdict (R9).
                raise
            except Exception:
                logger.exception(
                    "verdict answer-writer attempt %d/%d raised",
                    attempt,
                    VERDICT_MAX_ATTEMPTS,
                )
                continue
            parsed = _parse_verdict(raw)
            if parsed is not None:
                return parsed
            logger.warning(
                "verdict answer-writer attempt %d/%d returned no parseable JSON",
                attempt,
                VERDICT_MAX_ATTEMPTS,
            )
        return None

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
        """The verdict over the consensus window (the last two rounds).

        Stance, weight share, clusters and the supporting or opposing references all read the
        same window `weighted_share` reads, so the screen, the stop rule and the verdict show one
        number. With no position in the window the verdict is explicitly "no verdict"
        (overall ABSTAIN, zero share), never NEUTRAL.
        """
        window = consensus_window(rounds)
        profile_map = {p.identity.name: p for p in profiles}
        weights = stance_weights(window, profile_map)
        clusters = cluster_by_stance(window)

        cluster_details: dict[Stance, ClusterSummary] = {}
        for stance, turns in clusters.items():
            if not turns:
                continue
            cluster_details[stance] = ClusterSummary(
                stance=stance,
                count=len(turns),
                total_weight=weights[stance],
                avg_confidence=sum(t.confidence for t in turns) / len(turns),
                avg_conviction=sum(t.strength for t in turns) / len(turns),
                agents=[t.agent_name for t in turns],
            )

        consensus = weighted_share(window, profile_map)
        if consensus is None:
            return DebateVerdict(
                overall_stance=Stance.ABSTAIN,
                confidence_score=0.0,
                supporting_entities=[],
                opposing_entities=[],
                summary=NO_VERDICT_SUMMARY,
                cluster_details=cluster_details,
                rounds_executed=len(rounds),
                weight_share=0.0,
                contested=False,
            )

        overall_stance, weight_share = consensus
        # `confidence_score` keeps its long-standing number; `weight_share` is
        # the same value under its honest name. `contested` stops a near-tie
        # from reading as a mandate.
        confidence_score = weight_share
        contested = weight_share < CONTESTED_THRESHOLD

        supporting: list[str] = []
        opposing: list[str] = []
        provenance_by_claim: dict[str, list] = {}
        for turn in window:
            turn_stance = wire_stance(turn.stance)
            # No stance this turn, or ABSTAIN: the turn takes no side in the race.
            if turn_stance is None or turn_stance is Stance.ABSTAIN:
                continue
            if turn_stance == overall_stance:
                supporting.extend(turn.references)
            else:
                opposing.extend(turn.references)
            # Trace each claim back to provenance reachable from its speaker;
            # never fabricate — a turn with no references contributes nothing, and
            # a synthesized (sector-fallback) link is not real provenance, so it
            # is dropped rather than attributed to the claim.
            profile = profile_map.get(turn.agent_name)
            if profile is not None:
                for ref in turn.references:
                    links = provenance_by_claim.setdefault(ref, [])
                    for item in profile.evidence:
                        link = _provenance_link(item)
                        if link is not None and link not in links:
                            links.append(link)

        dominant_count = cluster_details[overall_stance].count
        dominant_pct = dominant_count / len(window) * 100

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
