"""Verdict synthesis quality: the consensus numbers.

Pins three properties of the consensus:
  - a declared strength of 0 carries no weight, and a strong minority can win,
  - a near-tie reads as a share, flagged contested,
  - `provenance_by_claim` is populated from reachable provenance, never faked.
"""

from uuid import uuid4

import pytest

from src.persona.agent import Agent, Stance
from src.simulation.evidence import EvidenceItem
from src.simulation.pair_turn import AgentTurn, RoundResult
from src.simulation.verdict import CONTESTED_THRESHOLD, VerdictSynthesizer
from tests.agent_factory import slim_agent

# --- fixtures ---------------------------------------------------------------


def make_turn(
    agent_name: str,
    stance: str,
    confidence: float,
    content: str | None = None,
    refs: list[str] | None = None,
    strength: float = 1.0,
) -> AgentTurn:
    return AgentTurn(
        agent_id=f"id-{agent_name}",
        agent_name=agent_name,
        content=content if content is not None else f"Argument from {agent_name}",
        stance=stance,
        confidence=confidence,
        references=refs or [],
        strength=strength,
    )


def make_round(num: int, turns: list[AgentTurn]) -> RoundResult:
    return RoundResult(round_num=num, turns=turns, pairs=[])


def make_agent(
    name: str,
    confidence: float = 0.5,
    provenance: list[EvidenceItem] | None = None,
) -> Agent:
    return slim_agent(name, confidence=confidence, evidence=provenance or [])


def provenance_of(title: str) -> EvidenceItem:
    return EvidenceItem(
        id=f"e-{title}",
        chunk_id=str(uuid4()),
        doc_id=f"doc-{title}",
        doc_title=title,
        section=title,
        span=(0, len(title)),
        text=title,
        origin="chunk",
        retrieval_score=1.0,
    )


class TestStrengthWeighting:
    def test_a_strong_minority_can_win(self):
        synthesizer = VerdictSynthesizer()
        rounds = [
            make_round(
                1,
                [
                    make_turn("Milquetoast", "POSITIVE", 0.4, strength=0.2),
                    make_turn("Gut", "NEGATIVE", 1.0, strength=1.0),
                ],
            )
        ]
        profiles = [
            make_agent("Milquetoast", confidence=0.4),
            make_agent("Gut", confidence=1.0),
        ]
        verdict = synthesizer.synthesize(rounds, profiles)
        assert verdict.overall_stance == Stance.NEGATIVE


# --- Step 6/7: honest share + contested flag --------------------------------


class TestWeightShare:
    def _near_tie(self) -> tuple[list[RoundResult], list[Agent]]:
        rounds = [
            make_round(
                1,
                [
                    make_turn("Alice", "POSITIVE", 0.51),
                    make_turn("Bob", "NEGATIVE", 0.49),
                ],
            )
        ]
        profiles = [make_agent("Alice", confidence=0.51), make_agent("Bob", confidence=0.49)]
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
            make_round(
                1,
                [
                    make_turn("Alice", "POSITIVE", 0.9),
                    make_turn("Bob", "NEGATIVE", 0.1),
                ],
            )
        ]
        profiles = [make_agent("Alice", confidence=0.9), make_agent("Bob", confidence=0.1)]
        verdict = VerdictSynthesizer().synthesize(rounds, profiles)
        assert verdict.contested is False
        assert verdict.weight_share >= CONTESTED_THRESHOLD


# --- Step 8: provenance_by_claim --------------------------------------------


class TestProvenanceByClaim:
    def test_claims_map_to_reachable_provenance(self):
        link_a = provenance_of("Market Report")
        rounds = [
            make_round(
                1,
                [
                    make_turn("Alice", "POSITIVE", 0.8, refs=["entity_alpha"]),
                ],
            )
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
