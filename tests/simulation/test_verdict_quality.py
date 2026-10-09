"""Task 8: verdict synthesis quality.

Pins four properties the final report must have:
  - the summary is grounded in the debate text (not a template count),
  - the CIOR factor never zeroes a cluster (a hostile dissenter still counts),
  - a near-tie reads as a share, flagged contested,
  - `provenance_by_claim` is populated from reachable provenance, never faked.
"""
from uuid import uuid4

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.persona.agent import (
    Agent,
    DiscoveryType,
    ExpertiseLevel,
    PersonaIdentity,
    ProvenanceLink,
    Stance,
)
from src.simulation.pair_turn import AgentTurn, RoundResult
from src.simulation.verdict import (
    CONTESTED_THRESHOLD,
    SUMMARY_TRANSCRIPT_MAX_CHARS,
    SUMMARY_TRANSCRIPT_MAX_TURNS,
    VerdictSynthesizer,
)


# --- fixtures ---------------------------------------------------------------


def make_turn(
    agent_name: str,
    stance: str,
    confidence: float,
    content: str | None = None,
    refs: list[str] | None = None,
) -> AgentTurn:
    return AgentTurn(
        agent_id=f"id-{agent_name}",
        agent_name=agent_name,
        content=content if content is not None else f"Argument from {agent_name}",
        stance=stance,
        confidence=confidence,
        references=refs or [],
    )


def make_round(num: int, turns: list[AgentTurn]) -> RoundResult:
    return RoundResult(round_num=num, turns=turns, pairs=[])


def make_agent(
    name: str,
    conviction: float = 1.0,
    cior: float = 1.0,
    provenance: list[ProvenanceLink] | None = None,
) -> Agent:
    return Agent(
        identity=PersonaIdentity(
            name=name, archetype="Expert", communication_style="direct"
        ),
        discovery_type=DiscoveryType.GRAPH_DISCOVERY,
        expertise_level=ExpertiseLevel.STRATEGIC,
        conviction=conviction,
        cior=cior,
        summary_provenance=provenance or [],
    )


def provenance_of(title: str) -> ProvenanceLink:
    return ProvenanceLink(
        doc_id=f"doc-{title}", title=title, breadcrumb=title, chunk_id=uuid4()
    )


class _SpyLLM:
    """Mock LLMClient.generate that records the prompts it was handed."""

    def __init__(self, reply: str = "GROUNDED SYNTHESIS"):
        self.reply = reply
        self.calls: list[dict] = []

    async def generate(self, system_prompt, user_prompt, **kwargs):
        self.calls.append({"system": system_prompt, "user": user_prompt})
        return self.reply

    @property
    def last_user_prompt(self) -> str:
        return self.calls[-1]["user"]


# --- Step 1/2/3: the summary is grounded in the debate text -----------------


class TestGroundedSummary:
    @pytest.mark.asyncio
    async def test_summary_is_the_llm_text(self):
        rounds = [
            make_round(1, [make_turn("Alice", "POSITIVE", 0.8)]),
            make_round(2, [make_turn("Bob", "NEGATIVE", 0.7)]),
        ]
        profiles = [make_agent("Alice"), make_agent("Bob")]
        llm = _SpyLLM(reply="The society leaned positive on the strength of Alice.")

        verdict = await VerdictSynthesizer().asynthesize(
            rounds=rounds, profiles=profiles, llm_client=llm
        )

        assert verdict.summary == "The society leaned positive on the strength of Alice."

    @pytest.mark.asyncio
    async def test_summary_prompt_carries_the_debate_text(self):
        rounds = [
            make_round(1, [make_turn("Alice", "POSITIVE", 0.8, content="Expand now, the metrics are strong.")]),
            make_round(2, [make_turn("Bob", "NEGATIVE", 0.7, content="The cash burn says wait.")]),
        ]
        profiles = [make_agent("Alice"), make_agent("Bob")]
        llm = _SpyLLM()

        await VerdictSynthesizer().asynthesize(
            rounds=rounds, profiles=profiles, llm_client=llm
        )

        prompt = llm.last_user_prompt
        assert "Expand now, the metrics are strong." in prompt
        assert "The cash burn says wait." in prompt
        assert "Alice" in prompt and "Bob" in prompt

    @pytest.mark.asyncio
    async def test_summary_falls_back_to_template_when_client_absent(self):
        rounds = [make_round(1, [make_turn("Alice", "POSITIVE", 0.8)])]
        verdict = await VerdictSynthesizer().asynthesize(
            rounds=rounds, profiles=[make_agent("Alice")], llm_client=None
        )
        assert "POSITIVE" in verdict.summary
        assert "Confidence score" in verdict.summary

    @pytest.mark.asyncio
    async def test_summary_falls_back_to_template_when_call_fails(self):
        rounds = [make_round(1, [make_turn("Alice", "POSITIVE", 0.8)])]
        boom = MagicMock()
        boom.generate = AsyncMock(side_effect=RuntimeError("provider down"))

        verdict = await VerdictSynthesizer().asynthesize(
            rounds=rounds, profiles=[make_agent("Alice")], llm_client=boom
        )

        assert "POSITIVE" in verdict.summary
        assert "Confidence score" in verdict.summary


# --- Step 9: transcript is bounded ------------------------------------------


class TestTranscriptBound:
    @pytest.mark.asyncio
    async def test_long_transcript_is_bounded(self):
        turns = [
            make_turn(
                f"Agent{i}",
                "POSITIVE",
                0.5,
                content=("long argument " * 20) + f"#{i}",
            )
            for i in range(60)
        ]
        rounds = [make_round(1, turns)]
        profiles = [make_agent(f"Agent{i}") for i in range(60)]
        llm = _SpyLLM()

        await VerdictSynthesizer().asynthesize(
            rounds=rounds, profiles=profiles, llm_client=llm
        )

        prompt = llm.last_user_prompt
        # transcript section cannot exceed the char cap (plus fixed framing).
        assert len(prompt) < SUMMARY_TRANSCRIPT_MAX_CHARS + 2000
        # aggregate numbers still ride along.
        assert "100" in prompt or "%" in prompt or "turns" in prompt.lower()

    @pytest.mark.asyncio
    async def test_only_last_n_turns_reach_the_prompt(self):
        turns = [
            make_turn(f"Agent{i}", "POSITIVE", 0.5, content=f"TURN-{i}")
            for i in range(SUMMARY_TRANSCRIPT_MAX_TURNS + 10)
        ]
        rounds = [make_round(1, turns)]
        profiles = [make_agent(f"Agent{i}") for i in range(len(turns))]
        llm = _SpyLLM()

        await VerdictSynthesizer().asynthesize(
            rounds=rounds, profiles=profiles, llm_client=llm
        )

        prompt = llm.last_user_prompt
        assert "TURN-0" not in prompt
        assert f"TURN-{len(turns) - 1}" in prompt


# --- Step 4/5: the CIOR factor never erases a cluster -----------------------


class TestCiorFloor:
    def test_hostile_cluster_weight_is_positive(self):
        synthesizer = VerdictSynthesizer()
        clusters = {s: [] for s in Stance}
        clusters[Stance.NEGATIVE] = [make_turn("Gut", "NEGATIVE", 1.0)]
        weights = synthesizer._calibrate_cior(
            clusters, {"Gut": make_agent("Gut", conviction=1.0, cior=-1.0)}
        )
        assert weights[Stance.NEGATIVE] > 0.0

    def test_cior_floor_maps_minus_one_to_half(self):
        synthesizer = VerdictSynthesizer()
        clusters = {s: [] for s in Stance}
        clusters[Stance.NEGATIVE] = [make_turn("Gut", "NEGATIVE", 1.0)]
        weights = synthesizer._calibrate_cior(
            clusters, {"Gut": make_agent("Gut", conviction=1.0, cior=-1.0)}
        )
        # cior_factor(-1) = 0.5 => weight = 1.0 * 1.0 * 0.5
        assert pytest.approx(weights[Stance.NEGATIVE], rel=1e-6) == 0.5

    def test_hostile_cluster_can_win(self):
        synthesizer = VerdictSynthesizer()
        rounds = [
            make_round(1, [
                make_turn("Milquetoast", "POSITIVE", 0.4),
                make_turn("Gut", "NEGATIVE", 1.0),
            ])
        ]
        profiles = [
            make_agent("Milquetoast", conviction=1.0, cior=1.0),
            make_agent("Gut", conviction=1.0, cior=-1.0),
        ]
        verdict = synthesizer.synthesize(rounds, profiles)
        assert verdict.overall_stance == Stance.NEGATIVE


# --- Step 6/7: honest share + contested flag --------------------------------


class TestWeightShare:
    def _near_tie(self) -> tuple[list[RoundResult], list[Agent]]:
        rounds = [
            make_round(1, [
                make_turn("Alice", "POSITIVE", 0.51),
                make_turn("Bob", "NEGATIVE", 0.49),
            ])
        ]
        profiles = [make_agent("Alice"), make_agent("Bob")]
        return rounds, profiles

    def test_weight_share_exposes_the_dominant_share(self):
        rounds, profiles = self._near_tie()
        verdict = VerdictSynthesizer().synthesize(rounds, profiles)
        assert pytest.approx(verdict.weight_share, rel=1e-6) == 0.51

    def test_confidence_score_is_unchanged_by_the_rename(self):
        rounds, profiles = self._near_tie()
        verdict = VerdictSynthesizer().synthesize(rounds, profiles)
        # back-compat: the existing key stays present, same number as the share.
        assert pytest.approx(verdict.confidence_score, rel=1e-6) == 0.51
        assert verdict.confidence_score == verdict.weight_share

    def test_near_tie_is_contested(self):
        rounds, profiles = self._near_tie()
        verdict = VerdictSynthesizer().synthesize(rounds, profiles)
        assert verdict.contested is True

    def test_clear_majority_is_not_contested(self):
        rounds = [
            make_round(1, [
                make_turn("Alice", "POSITIVE", 0.9),
                make_turn("Bob", "NEGATIVE", 0.1),
            ])
        ]
        profiles = [make_agent("Alice"), make_agent("Bob")]
        verdict = VerdictSynthesizer().synthesize(rounds, profiles)
        assert verdict.contested is False
        assert verdict.weight_share >= CONTESTED_THRESHOLD


# --- Step 8: provenance_by_claim --------------------------------------------


class TestProvenanceByClaim:
    def test_claims_map_to_reachable_provenance(self):
        link_a = provenance_of("Market Report")
        rounds = [
            make_round(1, [
                make_turn("Alice", "POSITIVE", 0.8, refs=["entity_alpha"]),
            ])
        ]
        profiles = [make_agent("Alice", provenance=[link_a])]

        verdict = VerdictSynthesizer().synthesize(rounds, profiles)

        assert "entity_alpha" in verdict.provenance_by_claim
        links = verdict.provenance_by_claim["entity_alpha"]
        assert [l.title for l in links] == ["Market Report"]

    def test_empty_when_turn_carried_no_references(self):
        rounds = [make_round(1, [make_turn("Alice", "POSITIVE", 0.8, refs=[])])]
        profiles = [make_agent("Alice", provenance=[provenance_of("Anything")])]
        verdict = VerdictSynthesizer().synthesize(rounds, profiles)
        assert verdict.provenance_by_claim == {}

    def test_empty_when_agent_has_no_provenance(self):
        rounds = [
            make_round(1, [make_turn("Alice", "POSITIVE", 0.8, refs=["entity_alpha"])])
        ]
        profiles = [make_agent("Alice", provenance=[])]
        verdict = VerdictSynthesizer().synthesize(rounds, profiles)
        assert verdict.provenance_by_claim.get("entity_alpha", []) == []
