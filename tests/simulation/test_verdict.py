"""Tests for VerdictSynthesizer."""

import json
import math
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.persona.agent import WIRE_STANCES, Stance
from src.simulation.pair_turn import AgentTurn, DebateVerdict, RoundResult
from src.simulation.turn_protocol import stance_weights
from src.simulation.verdict import (
    NO_VERDICT_STATUS,
    NO_VERDICT_SUMMARY,
    VerdictSynthesizer,
    cluster_by_stance,
)
from tests.agent_factory import slim_agent


def test_debate_verdict_has_narrative():
    v = DebateVerdict(
        overall_stance=Stance.NEUTRAL,
        confidence_score=0.0,
        supporting_entities=[],
        opposing_entities=[],
        summary="s",
        cluster_details={},
        narrative="## Recommendation\nYes.",
    )
    assert v.narrative.startswith("## Recommendation")


def make_profile(name: str, confidence: float = 0.5):
    return slim_agent(name, confidence=confidence)


def make_turn(
    agent_id: str,
    agent_name: str,
    stance: str,
    confidence: float,
    refs: list[str] | None = None,
    strength: float = 0.5,
) -> AgentTurn:
    return AgentTurn(
        agent_id=agent_id,
        agent_name=agent_name,
        content=f"Content from {agent_name}",
        stance=stance,
        confidence=confidence,
        references=refs or [],
        strength=strength,
    )


def make_round(num: int, turns: list[AgentTurn]) -> RoundResult:
    return RoundResult(round_num=num, turns=turns, pairs=[])


class TestRenderTranscript:
    """The answer-writer's transcript carries each stated answer, never the private reasoning."""

    def test_transcript_carries_the_answer_and_no_reasoning(self):
        synth = VerdictSynthesizer()
        turn = AgentTurn(
            agent_id="a1",
            agent_name="Alice",
            content="I support it.",
            stance="POSITIVE",
            confidence=0.8,
            strength=0.5,
        )
        text, _ = synth._render_transcript([turn])
        assert text == "[POSITIVE] Alice: I support it."


class TestClusterByStance:
    """Unit tests for cluster_by_stance: wire stances only, never a silent NEUTRAL."""

    def test_clusters_positive_negative(self):
        turns = [
            make_turn("a1", "Alice", "POSITIVE", 0.8),
            make_turn("a2", "Bob", "NEGATIVE", 0.6),
        ]
        clusters = cluster_by_stance(turns)
        assert len(clusters[Stance.POSITIVE]) == 1
        assert len(clusters[Stance.NEGATIVE]) == 1
        assert clusters[Stance.NEUTRAL] == []
        assert clusters[Stance.ABSTAIN] == []

    def test_unknown_stance_is_counted_in_no_cluster(self):
        turns = [make_turn("a1", "Alice", "UNKNOWN_STANCE", 0.5)]
        clusters = cluster_by_stance(turns)
        assert all(members == [] for members in clusters.values())

    def test_abstain_is_clustered_as_its_own_stance(self):
        turns = [make_turn("a1", "Alice", "ABSTAIN", 0.7)]
        clusters = cluster_by_stance(turns)
        assert len(clusters[Stance.ABSTAIN]) == 1


class TestAbstainCarriesNoWeight:
    """ABSTAIN is a wire stance with zero weight: it never wins and never shifts a share."""

    def test_abstain_turns_do_not_win_the_race(self):
        rounds = [
            make_round(
                1,
                [
                    make_turn("a1", "Alice", "ABSTAIN", 1.0),
                    make_turn("a2", "Bob", "ABSTAIN", 1.0),
                    make_turn("a3", "Carol", "POSITIVE", 1.0, strength=0.4),
                ],
            )
        ]
        profiles = [make_profile("Alice"), make_profile("Bob"), make_profile("Carol")]
        verdict = VerdictSynthesizer().synthesize(rounds, profiles)
        assert verdict.overall_stance is Stance.POSITIVE

    def test_all_abstain_is_no_verdict_and_never_neutral(self):
        rounds = [make_round(1, [make_turn("a1", "Alice", "ABSTAIN", 1.0)])]
        verdict = VerdictSynthesizer().synthesize(rounds, [make_profile("Alice")])
        assert verdict.overall_stance is Stance.ABSTAIN
        assert verdict.summary == NO_VERDICT_SUMMARY
        assert verdict.weight_share == 0.0

    def test_abstain_weighs_zero_in_the_stance_weights(self):
        turns = [make_turn("a1", "Alice", "ABSTAIN", 0.9, strength=1.0)]
        weights = stance_weights(turns, {"Alice": make_profile("Alice", confidence=1.0)})
        assert weights[Stance.ABSTAIN] == 0.0

    def test_weight_key_set_is_every_wire_stance(self):
        turns = [
            make_turn("a1", "Alice", "POSITIVE", 0.5),
            make_turn("a2", "Bob", "ABSTAIN", 0.5),
        ]
        profiles = {"Alice": make_profile("Alice"), "Bob": make_profile("Bob")}
        assert set(stance_weights(turns, profiles)) == set(WIRE_STANCES)


class TestSynthesize:
    """Integration tests for synthesize(): the verdict reads the last two rounds.

    Turn strength x profile confidence is each agent's weight: Alice 0.81, Bob 0.49 (round 1,
    outside the window), Carol 0.64, Dave 0.25, Eve 0.36, Frank 0.16.
    """

    @pytest.fixture
    def fixture_rounds(self):
        """3 rounds, 6 turns, mixed stances."""
        return [
            make_round(
                1,
                [
                    make_turn("a1", "Alice", "POSITIVE", 0.9, refs=["entity_alpha"], strength=0.9),
                    make_turn("a2", "Bob", "NEGATIVE", 0.7, refs=["entity_beta"], strength=0.7),
                ],
            ),
            make_round(
                2,
                [
                    make_turn(
                        "a3",
                        "Carol",
                        "POSITIVE",
                        0.8,
                        refs=["entity_alpha", "entity_gamma"],
                        strength=0.8,
                    ),
                    make_turn("a4", "Dave", "NEUTRAL", 0.5, refs=["entity_delta"], strength=0.5),
                ],
            ),
            make_round(
                3,
                [
                    make_turn("a5", "Eve", "POSITIVE", 0.6, refs=["entity_gamma"], strength=0.6),
                    make_turn("a6", "Frank", "NEGATIVE", 0.4, refs=["entity_epsilon"], strength=0.4),
                ],
            ),
        ]

    @pytest.fixture
    def fixture_profiles(self):
        """AgentProfiles matching fixture_rounds: confidence equals the turn confidence."""
        return [
            make_profile("Alice", confidence=0.9),
            make_profile("Bob", confidence=0.7),
            make_profile("Carol", confidence=0.8),
            make_profile("Dave", confidence=0.5),
            make_profile("Eve", confidence=0.6),
            make_profile("Frank", confidence=0.4),
        ]

    def test_empty_rounds_is_no_verdict_not_neutral(self):
        verdict = VerdictSynthesizer().synthesize([], [])
        assert verdict.overall_stance is Stance.ABSTAIN
        assert verdict.summary == NO_VERDICT_SUMMARY
        assert verdict.confidence_score == 0.0

    def test_empty_turns_is_no_verdict_not_neutral(self):
        verdict = VerdictSynthesizer().synthesize([make_round(1, [])], [])
        assert verdict.overall_stance is Stance.ABSTAIN
        assert verdict.summary == NO_VERDICT_SUMMARY

    def test_overall_stance_is_the_max_weight_cluster_in_the_window(
        self, fixture_rounds, fixture_profiles
    ):
        # Window (rounds 2-3): POSITIVE 0.64 + 0.36 = 1.00, NEGATIVE 0.16, NEUTRAL 0.25.
        verdict = VerdictSynthesizer().synthesize(fixture_rounds, fixture_profiles)
        assert verdict.overall_stance is Stance.POSITIVE

    def test_cluster_weights_are_the_window_weights(self, fixture_rounds, fixture_profiles):
        verdict = VerdictSynthesizer().synthesize(fixture_rounds, fixture_profiles)
        pos = verdict.cluster_details[Stance.POSITIVE]
        neg = verdict.cluster_details[Stance.NEGATIVE]
        neu = verdict.cluster_details[Stance.NEUTRAL]
        assert pytest.approx(pos.total_weight, rel=1e-6) == 1.00
        assert pytest.approx(neg.total_weight, rel=1e-6) == 0.16
        assert pytest.approx(neu.total_weight, rel=1e-6) == 0.25

    def test_a_round_outside_the_window_does_not_count(self, fixture_rounds, fixture_profiles):
        verdict = VerdictSynthesizer().synthesize(fixture_rounds, fixture_profiles)
        assert verdict.cluster_details[Stance.POSITIVE].agents == ["Carol", "Eve"]

    def test_avg_conviction_is_the_mean_declared_strength(self, fixture_rounds, fixture_profiles):
        verdict = VerdictSynthesizer().synthesize(fixture_rounds, fixture_profiles)
        assert pytest.approx(verdict.cluster_details[Stance.POSITIVE].avg_conviction) == 0.7

    def test_confidence_score_is_the_dominant_share(self, fixture_rounds, fixture_profiles):
        verdict = VerdictSynthesizer().synthesize(fixture_rounds, fixture_profiles)
        assert 0.0 <= verdict.confidence_score <= 1.0
        assert pytest.approx(verdict.confidence_score, rel=1e-6) == 1.00 / 1.41

    def test_rounds_executed_populated(self, fixture_rounds, fixture_profiles):
        verdict = VerdictSynthesizer().synthesize(fixture_rounds, fixture_profiles)
        assert verdict.rounds_executed == 3

    def test_supporting_opposing_entities_come_from_the_window(
        self, fixture_rounds, fixture_profiles
    ):
        verdict = VerdictSynthesizer().synthesize(fixture_rounds, fixture_profiles)
        # POSITIVE is the overall stance, so Carol's and Eve's refs support it.
        assert "entity_alpha" in verdict.supporting_entities
        assert "entity_gamma" in verdict.supporting_entities
        # Dave (neutral) and Frank (negative) oppose it; round 1 is outside the window.
        assert "entity_delta" in verdict.opposing_entities
        assert "entity_epsilon" in verdict.opposing_entities
        assert "entity_beta" not in verdict.opposing_entities

    def test_cluster_details_has_every_stance_with_window_turns(
        self, fixture_rounds, fixture_profiles
    ):
        verdict = VerdictSynthesizer().synthesize(fixture_rounds, fixture_profiles)
        assert Stance.POSITIVE in verdict.cluster_details
        assert Stance.NEGATIVE in verdict.cluster_details
        assert Stance.NEUTRAL in verdict.cluster_details

    def test_summary_contains_stance_and_score(self, fixture_rounds, fixture_profiles):
        verdict = VerdictSynthesizer().synthesize(fixture_rounds, fixture_profiles)
        assert "POSITIVE" in verdict.summary
        assert "Confidence score" in verdict.summary


class TestMissingProfileFailsClosed:
    """A speaker absent from the profiles is a broken run: the verdict raises, it never guesses."""

    def test_a_speaker_missing_from_the_profiles_raises(self):
        rounds = [make_round(1, [make_turn("a1", "Ghost", "POSITIVE", 0.8)])]
        with pytest.raises(ValueError):
            VerdictSynthesizer().synthesize(rounds, [make_profile("Alice")])

    def test_a_zero_strength_turn_carries_zero_weight(self):
        rounds = [make_round(1, [make_turn("g1", "GutAgent", "NEGATIVE", 1.0, strength=0.0)])]
        verdict = VerdictSynthesizer().synthesize(rounds, [make_profile("GutAgent", confidence=1.0)])
        assert verdict.cluster_details[Stance.NEGATIVE].total_weight == 0.0
        assert verdict.overall_stance is Stance.ABSTAIN

    def test_a_known_agent_weight_is_strength_times_confidence(self):
        rounds = [make_round(1, [make_turn("a1", "Alice", "POSITIVE", 0.5, strength=0.8)])]
        verdict = VerdictSynthesizer().synthesize(rounds, [make_profile("Alice", confidence=0.5)])
        assert math.isclose(verdict.cluster_details[Stance.POSITIVE].total_weight, 0.4)


def _answer_writer() -> MagicMock:
    llm = MagicMock()
    llm.generate = AsyncMock(
        return_value=json.dumps({"answer": "Expand.", "reasoning": "Because.", "constraints_and_risks": ""})
    )
    return llm


@pytest.mark.asyncio
async def test_no_verdict_skips_the_answer_writer_and_says_so():
    llm = _answer_writer()
    rounds = [make_round(1, [make_turn("a1", "Alice", "ABSTAIN", 1.0)])]
    verdict = await VerdictSynthesizer().asynthesize(
        rounds, [make_profile("Alice")], llm_client=llm
    )
    llm.generate.assert_not_awaited()
    assert verdict.narrative == NO_VERDICT_SUMMARY
    assert verdict.narrative_status == NO_VERDICT_STATUS


@pytest.mark.asyncio
async def test_the_answer_writer_reads_only_the_consensus_window():
    llm = _answer_writer()
    rounds = [
        make_round(1, [make_turn("a1", "Alice", "POSITIVE", 0.9)]),
        make_round(2, [make_turn("a2", "Bob", "NEGATIVE", 0.8)]),
        make_round(3, [make_turn("a3", "Carol", "NEGATIVE", 0.7)]),
    ]
    profiles = [
        make_profile("Alice", confidence=0.9),
        make_profile("Bob", confidence=0.8),
        make_profile("Carol", confidence=0.7),
    ]
    await VerdictSynthesizer().asynthesize(rounds, profiles, llm_client=llm)
    prompt = llm.generate.call_args.kwargs["user_prompt"]
    assert "Content from Alice" not in prompt
    assert "Content from Bob" in prompt
    assert "Content from Carol" in prompt
