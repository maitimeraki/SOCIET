"""Tests for pair_turn types."""
from dataclasses import fields

from src.simulation.pair_turn import (
    AgentTurn,
    RoundResult,
    DebateResult,
    ClusterSummary,
    DebateVerdict,
)


class TestPairTurnImports:
    """Types are importable from src.simulation.pair_turn."""

    def test_agent_turn_from_pair_turn(self):
        turn = AgentTurn(agent_id="a1", agent_name="Alice", content="Hi", stance="POS", confidence=0.8)
        assert turn.agent_id == "a1"
        assert turn.references == []

    def test_round_result_from_pair_turn(self):
        result = RoundResult(round_num=1, turns=[], pairs=[])
        assert result.round_num == 1

    def test_debate_result_from_pair_turn(self):
        result = DebateResult(query="test", rounds=[], converged=False, final_stances={}, verdict="ok")
        assert result.query == "test"

    def test_cluster_summary_from_pair_turn(self):
        from src.persona.agent import Stance
        summary = ClusterSummary(stance=Stance.POSITIVE, count=5, total_weight=1.0, avg_confidence=0.7, avg_conviction=0.5, agents=[])
        assert summary.stance == Stance.POSITIVE


class TestDebateVerdictNewFields:
    """DebateVerdict has the new fields: provenance_by_claim, rounds_executed."""

    def test_provenance_by_claim_default_empty(self):
        from src.persona.agent import Stance
        verdict = DebateVerdict(
            overall_stance=Stance.NEUTRAL,
            confidence_score=0.5,
            supporting_entities=[],
            opposing_entities=[],
            summary="test",
            cluster_details={},
        )
        assert verdict.provenance_by_claim == {}
        assert isinstance(verdict.provenance_by_claim, dict)

    def test_rounds_executed_default_zero(self):
        from src.persona.agent import Stance
        verdict = DebateVerdict(
            overall_stance=Stance.NEUTRAL,
            confidence_score=0.5,
            supporting_entities=[],
            opposing_entities=[],
            summary="test",
            cluster_details={},
        )
        assert verdict.rounds_executed == 0
        assert isinstance(verdict.rounds_executed, int)

    def test_provenance_by_claim_can_be_set(self):
        from src.persona.agent import Stance
        from src.persona.models_persona import ProvenanceLink
        from uuid import uuid4

        link = ProvenanceLink(doc_id="d1", title="Doc", breadcrumb="a > b", chunk_id=uuid4())
        verdict = DebateVerdict(
            overall_stance=Stance.POSITIVE,
            confidence_score=0.8,
            supporting_entities=["e1"],
            opposing_entities=[],
            summary="ok",
            cluster_details={},
            provenance_by_claim={"claim1": [link]},
            rounds_executed=5,
        )
        assert verdict.provenance_by_claim == {"claim1": [link]}
        assert verdict.rounds_executed == 5

    def test_debate_verdict_has_new_fields(self):
        pair_turn_fields = {f.name for f in fields(DebateVerdict)}
        assert "provenance_by_claim" in pair_turn_fields
        assert "rounds_executed" in pair_turn_fields
