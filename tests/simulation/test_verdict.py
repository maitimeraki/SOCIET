"""Tests for VerdictSynthesizer."""
import pytest
from unittest.mock import MagicMock

from src.simulation.verdict import VerdictSynthesizer
from src.simulation.pair_turn import RoundResult, AgentTurn
from src.simulation.agent_node import Stance


class MockProfile:
    """Minimal stand-in for AgentProfile, compatible with _calibrate_cior lookups."""
    def __init__(self, name: str, conviction: float, cior: float):
        identity = MagicMock()
        identity.name = name
        self.identity = identity
        self.conviction = conviction
        self.cior = cior


def make_profile(name: str, conviction: float = 0.5, cior: float = 0.0) -> MockProfile:
    return MockProfile(name=name, conviction=conviction, cior=cior)


def make_turn(agent_id: str, agent_name: str, stance: str, confidence: float, refs: list[str] | None = None) -> AgentTurn:
    return AgentTurn(
        agent_id=agent_id,
        agent_name=agent_name,
        content=f"Content from {agent_name}",
        stance=stance,
        confidence=confidence,
        references=refs or [],
    )


def make_round(num: int, turns: list[AgentTurn]) -> RoundResult:
    return RoundResult(round_num=num, turns=turns, pairs=[])


class TestClusterOpinions:
    """Unit tests for _cluster_opinions."""

    def test_clusters_positive_negative(self):
        synthesizer = VerdictSynthesizer()
        turns = [
            make_turn("a1", "Alice", "POSITIVE", 0.8),
            make_turn("a2", "Bob", "NEGATIVE", 0.6),
        ]
        clusters = synthesizer._cluster_opinions(turns)
        assert len(clusters[Stance.POSITIVE]) == 1
        assert len(clusters[Stance.NEGATIVE]) == 1
        assert clusters[Stance.NEUTRAL] == []
        assert clusters[Stance.AMBIVALENT] == []

    def test_clusters_unknown_stance_falls_back_to_neutral(self):
        synthesizer = VerdictSynthesizer()
        turns = [make_turn("a1", "Alice", "UNKNOWN_STANCE", 0.5)]
        clusters = synthesizer._cluster_opinions(turns)
        assert len(clusters[Stance.NEUTRAL]) == 1

    def test_clusters_stance_object(self):
        synthesizer = VerdictSynthesizer()
        turns = [make_turn("a1", "Alice", Stance.AMBIVALENT, 0.7)]
        clusters = synthesizer._cluster_opinions(turns)
        assert len(clusters[Stance.AMBIVALENT]) == 1


class TestCalibrateCIOR:
    """Unit tests for _calibrate_cior."""

    def test_weights_zero_for_empty_clusters(self):
        synthesizer = VerdictSynthesizer()
        clusters = {s: [] for s in Stance}
        weights = synthesizer._calibrate_cior(clusters, {})
        assert all(w == 0.0 for w in weights.values())

    def test_unrecognized_agent_uses_confidence_half(self):
        synthesizer = VerdictSynthesizer()
        clusters = {s: [] for s in Stance}
        clusters[Stance.POSITIVE] = [make_turn("unknown", "Unknown", "POSITIVE", 0.8)]
        weights = synthesizer._calibrate_cior(clusters, {})  # no profiles
        # weight = confidence * 0.5 = 0.4
        assert pytest.approx(weights[Stance.POSITIVE], rel=1e-6) == 0.4

    def test_known_agent_uses_conviction_and_cior(self):
        synthesizer = VerdictSynthesizer()
        p_alice = make_profile("Alice", conviction=0.8, cior=0.5)  # cior_factor = 0.75
        clusters = {s: [] for s in Stance}
        clusters[Stance.POSITIVE] = [make_turn("a1", "Alice", "POSITIVE", 0.5)]
        weights = synthesizer._calibrate_cior(clusters, {"Alice": p_alice})
        # weight = 0.5 * 0.8 * 0.75 = 0.3
        assert pytest.approx(weights[Stance.POSITIVE], rel=1e-6) == 0.3

    def test_cior_negative_reduces_weight(self):
        synthesizer = VerdictSynthesizer()
        p_gut = make_profile("GutAgent", conviction=1.0, cior=-1.0)  # cior_factor = 0
        clusters = {s: [] for s in Stance}
        clusters[Stance.NEGATIVE] = [make_turn("g1", "GutAgent", "NEGATIVE", 1.0)]
        weights = synthesizer._calibrate_cior(clusters, {"GutAgent": p_gut})
        # weight = 1.0 * 1.0 * 0 = 0
        assert pytest.approx(weights[Stance.NEGATIVE], rel=1e-6) == 0.0


class TestSynthesize:
    """Integration tests for synthesize()."""

    @pytest.fixture
    def fixture_rounds(self):
        """3 rounds, 6 turns, mixed stances."""
        return [
            make_round(1, [
                make_turn("a1", "Alice", "POSITIVE", 0.9, refs=["entity_alpha"]),
                make_turn("a2", "Bob", "NEGATIVE", 0.7, refs=["entity_beta"]),
            ]),
            make_round(2, [
                make_turn("a3", "Carol", "POSITIVE", 0.8, refs=["entity_alpha", "entity_gamma"]),
                make_turn("a4", "Dave", "NEUTRAL", 0.5, refs=["entity_delta"]),
            ]),
            make_round(3, [
                make_turn("a5", "Eve", "POSITIVE", 0.6, refs=["entity_gamma"]),
                make_turn("a6", "Frank", "NEGATIVE", 0.4, refs=["entity_epsilon"]),
            ]),
        ]

    @pytest.fixture
    def fixture_profiles(self):
        """AgentProfiles matching fixture_rounds (cior=1.0 => cior_factor=1.0)."""
        return [
            make_profile("Alice", conviction=0.9, cior=1.0),
            make_profile("Bob",   conviction=0.7, cior=1.0),
            make_profile("Carol", conviction=0.8, cior=1.0),
            make_profile("Dave",  conviction=0.5, cior=1.0),
            make_profile("Eve",   conviction=0.6, cior=1.0),
            make_profile("Frank", conviction=0.4, cior=1.0),
        ]

    def test_empty_rounds_returns_neutral(self):
        synthesizer = VerdictSynthesizer()
        verdict = synthesizer.synthesize([], [])
        assert verdict.overall_stance == Stance.NEUTRAL
        assert verdict.confidence_score == 0.0

    def test_empty_turns_returns_neutral(self):
        synthesizer = VerdictSynthesizer()
        verdict = synthesizer.synthesize([make_round(1, [])], [])
        assert verdict.overall_stance == Stance.NEUTRAL

    def test_overall_stance_is_max_weight_cluster(self, fixture_rounds, fixture_profiles):
        synthesizer = VerdictSynthesizer()
        # POSITIVE: Alice(0.9*0.9) + Carol(0.8*0.8) + Eve(0.6*0.6) = 0.81 + 0.64 + 0.36 = 1.81
        # NEGATIVE: Bob(0.7*0.7) + Frank(0.4*0.4) = 0.49 + 0.16 = 0.65
        # NEUTRAL:  Dave(0.5*0.5) = 0.25
        # max = POSITIVE
        verdict = synthesizer.synthesize(fixture_rounds, fixture_profiles)
        assert verdict.overall_stance == Stance.POSITIVE

    def test_cluster_weights_correct(self, fixture_rounds, fixture_profiles):
        synthesizer = VerdictSynthesizer()
        verdict = synthesizer.synthesize(fixture_rounds, fixture_profiles)
        pos = verdict.cluster_details[Stance.POSITIVE]
        neg = verdict.cluster_details[Stance.NEGATIVE]
        neu = verdict.cluster_details[Stance.NEUTRAL]
        assert pytest.approx(pos.total_weight, rel=1e-6) == 1.81
        assert pytest.approx(neg.total_weight, rel=1e-6) == 0.65
        assert pytest.approx(neu.total_weight, rel=1e-6) == 0.25

    def test_confidence_score_in_range(self, fixture_rounds, fixture_profiles):
        synthesizer = VerdictSynthesizer()
        verdict = synthesizer.synthesize(fixture_rounds, fixture_profiles)
        # total = 2.71, max = 1.81, score = 1.81/2.71
        assert 0.0 <= verdict.confidence_score <= 1.0
        assert pytest.approx(verdict.confidence_score, rel=1e-6) == 1.81 / 2.71

    def test_rounds_executed_populated(self, fixture_rounds, fixture_profiles):
        synthesizer = VerdictSynthesizer()
        verdict = synthesizer.synthesize(fixture_rounds, fixture_profiles)
        assert verdict.rounds_executed == 3

    def test_supporting_opposing_entities(self, fixture_rounds, fixture_profiles):
        synthesizer = VerdictSynthesizer()
        verdict = synthesizer.synthesize(fixture_rounds, fixture_profiles)
        # POSITIVE = overall stance, so refs from Alice, Carol, Eve are supporting
        assert "entity_alpha" in verdict.supporting_entities
        assert "entity_gamma" in verdict.supporting_entities
        # refs from Bob, Frank, Dave (neutral) are opposing
        assert "entity_beta" in verdict.opposing_entities
        assert "entity_epsilon" in verdict.opposing_entities
        assert "entity_delta" in verdict.opposing_entities

    def test_cluster_details_has_all_stances_with_turns(self, fixture_rounds, fixture_profiles):
        synthesizer = VerdictSynthesizer()
        verdict = synthesizer.synthesize(fixture_rounds, fixture_profiles)
        assert Stance.POSITIVE in verdict.cluster_details
        assert Stance.NEGATIVE in verdict.cluster_details
        assert Stance.NEUTRAL in verdict.cluster_details
        assert Stance.AMBIVALENT not in verdict.cluster_details  # no ambivalent turns

    def test_summary_contains_stance_and_score(self, fixture_rounds, fixture_profiles):
        synthesizer = VerdictSynthesizer()
        verdict = synthesizer.synthesize(fixture_rounds, fixture_profiles)
        assert "POSITIVE" in verdict.summary
        assert "Confidence score" in verdict.summary
