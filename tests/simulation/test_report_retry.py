"""The verdict retry's pure logic: the turn log, the rebuild from stored rows, and the exactness checks.

No database: the stored shapes are built as the debate stores them (round events as the projector
keeps them, the published record as the JSON the store keeps), and every rebuilt value is compared
with the in-memory original.
"""

import dataclasses
import json

import pytest

from src.persona.agent import Agent, PersonaIdentity, Stance
from src.simulation import report_retry as rr
from src.simulation.evidence import EvidenceItem, RelationItem
from src.simulation.pair_turn import AgentTurn, RoundResult
from src.simulation.verdict import (
    NOT_PRODUCED,
    PRODUCED,
    VerdictSynthesizer,
    board_facts,
    board_final_stances,
    build_report_bundle,
)


def _evidence(item_id: str, text: str) -> EvidenceItem:
    return EvidenceItem(
        id=item_id, chunk_id=f"chunk-{item_id}", doc_id="doc-memo", doc_title="Memo",
        section=f"Section {item_id}", span=(0, len(text)), text=text, origin="vector",
        retrieval_score=0.5,
    )


def _agent(name: str, stance: Stance, confidence: float, evidence: list[EvidenceItem]) -> Agent:
    return Agent(
        node_id=f"node-{name.lower()}",
        dataset_id="ds-1",
        identity=PersonaIdentity(name=name, type_label="Company"),
        role="analyst",
        stance=stance,
        strength=0.7,
        confidence=confidence,
        bio=f"{name} bio.",
        details_raw=f"{name} details [e1].",
        evidence=evidence,
        relations=[RelationItem(id="r1", type="supports", direction="out", counterpart_id="x",
                                counterpart_name="Lumen", chunk_id="chunk-e1")],
        cites={"stance": ["e1"], "details": ["e1"]},
    )


def _turn(agent: Agent, stance: str, cites: tuple[str, ...], strength: float, content: str) -> AgentTurn:
    return AgentTurn(
        agent_id=str(agent.agent_id), agent_name=agent.identity.name, content=content, stance=stance,
        confidence=agent.confidence, strength=strength, references=["Lumen"], cites=cites,
    )


@pytest.fixture
def board():
    kestra = _agent("Kestra", Stance.POSITIVE, 0.8, [_evidence("e1", "Revenue grew twelve percent.")])
    orbit = _agent("Orbit", Stance.NEGATIVE, 0.5, [_evidence("e1", "Margins fell this year."),
                                                   _evidence("e2", "Churn is rising.")])
    rounds = [
        RoundResult(round_num=1, turns=[
            _turn(kestra, "POSITIVE", ("e1",), 0.6, "Growth supports entry."),
            _turn(orbit, "NEGATIVE", ("e2",), 0.4, "Churn argues against."),
        ], pairs=[]),
        RoundResult(round_num=2, turns=[
            _turn(kestra, "POSITIVE", ("e1",), 0.7, "Still for entry."),
            _turn(orbit, "NEGATIVE", ("e1", "e2"), 0.8, "Margins and churn argue against."),
        ], pairs=[]),
    ]
    return rounds, [kestra, orbit]


def _events(rounds: list[RoundResult]) -> list[dict]:
    """Round events as the projector keeps them: no cites, no strength."""
    return [
        {
            "type": "round",
            "round": round_result.round_num,
            "turns": [
                {"agent_id": t.agent_id, "agent_name": t.agent_name, "content": t.content,
                 "stance": t.stance, "confidence": t.confidence, "references": t.references}
                for t in round_result.turns
            ],
        }
        for round_result in rounds
    ]


def _records(profiles: list[Agent]) -> list[dict]:
    """Published records as the store keeps them: JSON of the record, with the view."""
    return [
        json.loads(json.dumps({
            "node_id": agent.node_id,
            "node": {"name": agent.identity.name, "type_label": agent.identity.type_label},
            "view": agent.view().model_dump(mode="json"),
            "details_raw": agent.details_raw,
            "evidence": [dataclasses.asdict(item) for item in agent.evidence],
            "relations": [dataclasses.asdict(relation) for relation in agent.relations],
            "cites": agent.cites,
        }))
        for agent in profiles
    ]


def _stored(rounds, profiles, converged=True) -> dict:
    """The stored verdict fields the rebuild is checked against, as the debate stores them."""
    verdict = VerdictSynthesizer().synthesize(rounds=rounds, profiles=profiles)
    return {
        "converged": converged,
        "rounds_executed": len(rounds),
        "final_stances": board_final_stances(rounds, profiles),
        "weight_share": verdict.weight_share,
        "position": board_facts(rounds, profiles, converged).position.value,
    }


def test_the_turn_log_and_round_events_rebuild_the_rounds_exactly(board):
    rounds, _ = board
    inputs = json.loads(json.dumps(rr.build_retry_inputs(rounds, "scenario text")))

    assert rr.rebuild_rounds(_events(rounds), inputs) == rounds


def test_the_turn_log_keeps_the_context_and_one_entry_per_turn(board):
    rounds, _ = board
    inputs = rr.build_retry_inputs(rounds, "scenario text")

    assert inputs["context"] == "scenario text"
    assert len(inputs["turns"]) == 4
    assert inputs["turns"][0] == {"agent_name": "Kestra", "round": 1, "stance": "POSITIVE",
                                  "cites": ["e1"], "strength": 0.6}


def test_a_turn_log_over_its_bound_is_not_kept(board):
    rounds, _ = board
    crowded = [RoundResult(round_num=1, turns=rounds[0].turns * (rr.RETRY_TURN_LOG_MAX // 2 + 1), pairs=[])]

    assert rr.build_retry_inputs(crowded, "") is None


def test_the_rebuilt_profiles_equal_the_seated_agents(board):
    _, profiles = board
    rebuilt = rr.rebuild_profiles(_records(profiles), "ds-1")

    assert [a.model_dump(exclude={"agent_id"}) for a in rebuilt] == [
        a.model_dump(exclude={"agent_id"}) for a in profiles
    ]


def test_the_rebuilt_bundle_and_board_equal_the_debate_bundle(board):
    rounds, profiles = board
    inputs = json.loads(json.dumps(rr.build_retry_inputs(rounds, "scenario text")))
    rebuilt_rounds = rr.rebuild_rounds(_events(rounds), inputs)
    rebuilt_profiles = rr.rebuild_profiles(_records(profiles), "ds-1")

    original = build_report_bundle(rounds, profiles, "Q?", "scenario text")
    rebuilt = build_report_bundle(rebuilt_rounds, rebuilt_profiles, "Q?", "scenario text")

    assert original[0].sources
    assert rebuilt == original
    assert board_facts(rebuilt_rounds, rebuilt_profiles, True) == board_facts(rounds, profiles, True)


def test_the_stored_board_passes_the_check(board):
    rounds, profiles = board

    rr.check_rebuild(rounds, profiles, _stored(rounds, profiles))


@pytest.mark.parametrize(
    "key, value",
    [
        ("rounds_executed", 3),
        ("final_stances", {"Kestra": "POSITIVE", "Orbit": "POSITIVE"}),
        ("weight_share", 0.123),
        ("position", "NEGATIVE"),
    ],
)
def test_a_rebuild_that_differs_from_the_stored_board_is_refused(board, key, value):
    rounds, profiles = board
    stored = {**_stored(rounds, profiles), key: value}

    with pytest.raises(rr.RetryDataError):
        rr.check_rebuild(rounds, profiles, stored)


def test_a_turn_speaker_that_is_not_seated_is_refused(board):
    rounds, profiles = board
    stored = _stored(rounds, profiles)
    rounds[0].turns[0] = dataclasses.replace(rounds[0].turns[0], agent_name="Nobody")

    with pytest.raises(rr.RetryDataError):
        rr.check_rebuild(rounds, profiles, stored)


def test_a_turn_log_that_disagrees_with_the_events_is_refused(board):
    rounds, _ = board
    events = _events(rounds)
    inputs = rr.build_retry_inputs(rounds, "")

    wrong_speaker = json.loads(json.dumps(inputs))
    wrong_speaker["turns"][0]["agent_name"] = "Orbit"
    with pytest.raises(rr.RetryDataError):
        rr.rebuild_rounds(events, wrong_speaker)

    missing_turn = json.loads(json.dumps(inputs))
    missing_turn["turns"].pop()
    with pytest.raises(rr.RetryDataError):
        rr.rebuild_rounds(events, missing_turn)

    unknown_round = json.loads(json.dumps(inputs))
    unknown_round["turns"].append({**unknown_round["turns"][0], "round": 9})
    with pytest.raises(rr.RetryDataError):
        rr.rebuild_rounds(events, unknown_round)


@pytest.mark.parametrize(
    "result, code",
    [
        (None, rr.REFUSAL_NOT_PENDING),
        ({"status": PRODUCED, "retry_inputs": {"context": "", "turns": []}}, rr.REFUSAL_NOT_PENDING),
        ({"status": NOT_PRODUCED}, rr.REFUSAL_NOT_RETRYABLE),
        ({"status": NOT_PRODUCED, "retry_inputs": "not a mapping"}, rr.REFUSAL_NOT_RETRYABLE),
        ("not a mapping", rr.REFUSAL_NOT_PENDING),
    ],
)
def test_a_retry_is_refused_unless_the_report_is_pending_with_its_inputs(result, code):
    assert rr.retry_refusal(result) == code


def test_a_not_produced_run_with_its_inputs_may_retry():
    assert rr.retry_refusal({"status": NOT_PRODUCED, "retry_inputs": {"context": "", "turns": []}}) is None


def test_every_refusal_code_has_a_client_message():
    assert set(rr.REFUSAL_MESSAGES) == {rr.REFUSAL_NOT_PENDING, rr.REFUSAL_NOT_RETRYABLE, rr.REFUSAL_IN_FLIGHT}
