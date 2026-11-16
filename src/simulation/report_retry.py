"""The inputs a verdict retry rebuilds a report from, and the checks that the rebuild is exact.

BACKEND-ONLY. The debate writes `retry_inputs` into its stored result (context and the per-turn
evidence cites and strength); the retry job reads it back with the run's own rows: the round
events (turn content, references), the published agent records and the stored verdict. The
client never sees any of it (public_events keeps `retry_inputs` out of every served key).
"""

from collections.abc import Mapping, Sequence
from typing import Any, Optional

from src.persona.agent import Agent, PersonaIdentity, Stance
from src.simulation.evidence import EvidenceItem, RelationItem
from src.simulation.pair_turn import AgentTurn, RoundResult
from src.simulation.turn_protocol import consensus_window, weighted_share
from src.simulation.verdict import (
    NOT_PRODUCED,
    board_facts,
    board_final_stances,
    build_report_bundle,
)

#: The most turn-log entries a debate keeps. The plan caps bound a run far under this (agents
#: <= 12, pairs <= agents, rounds <= 20: at most 480 turns). A run over it keeps no retry inputs
#: and is answered as not retryable, never truncated.
RETRY_TURN_LOG_MAX = 1000

#: The stable refusal codes of the retry route, with their client messages.
REFUSAL_NOT_PENDING = "report_not_pending"
REFUSAL_NOT_RETRYABLE = "report_not_retryable"
REFUSAL_IN_FLIGHT = "retry_in_progress"
REFUSAL_MESSAGES = {
    REFUSAL_NOT_PENDING: "This run has no report that was not produced, so there is nothing to retry.",
    REFUSAL_NOT_RETRYABLE: "This run kept no inputs for a retry, so its report cannot be retried.",
    REFUSAL_IN_FLIGHT: "A retry for this report is already queued or running.",
}


class RetryDataError(ValueError):
    """The stored run cannot rebuild its report exactly. The reason is logged, never served."""


def board_fingerprint(rounds: Sequence[RoundResult], profiles: Sequence[Agent], query: str, scenario: str) -> dict[str, Any]:
    """What the report's bundle is made of, as the debate sees it: the source numbers, each citizen's
    name, position and cited source ids, and the switch lines. The rebuild must reproduce it exactly."""
    bundle, _refs = build_report_bundle(list(rounds), list(profiles), query, scenario)
    return {
        "sources": sorted(bundle.sources, key=int),
        # Sorted by name: the fingerprint says what the bundle holds, not the order its citizens were listed in.
        "citizens": sorted(
            (
                [citizen.name, citizen.position.value if citizen.position is not None else None, list(citizen.source_ids)]
                for citizen in bundle.citizens
            ),
            key=lambda row: row[0],
        ),
        "switches": list(bundle.switches),
    }


def build_retry_inputs(
    rounds: Sequence[RoundResult], profiles: Sequence[Agent], query: str, scenario: str
) -> Optional[dict[str, Any]]:
    """The backend-only inputs of a retry, or None when the turn log is over RETRY_TURN_LOG_MAX.

    `board` is the bundle fingerprint at debate time: check_rebuild compares the rebuilt bundle with it.
    """
    turns = [
        {
            "agent_name": turn.agent_name,
            "round": round_result.round_num,
            "stance": turn.stance,
            "cites": list(turn.cites),
            "strength": turn.strength,
        }
        for round_result in rounds
        for turn in round_result.turns
    ]
    if len(turns) > RETRY_TURN_LOG_MAX:
        return None
    return {
        "context": scenario,
        "turns": turns,
        "board": board_fingerprint(rounds, profiles, query, scenario),
    }


def retry_refusal(result: Any) -> Optional[str]:
    """The refusal code for a run's stored result, or None when a retry may start.

    A retry needs a report that was not produced (a running run and a run with no verdict are
    both "not pending"), and the inputs it was stored with.
    """
    if not isinstance(result, Mapping) or result.get("status") != NOT_PRODUCED:
        return REFUSAL_NOT_PENDING
    if not isinstance(result.get("retry_inputs"), Mapping):
        return REFUSAL_NOT_RETRYABLE
    return None


def agent_from_record(record: Mapping[str, Any], dataset_id: str) -> Agent:
    """A seated agent rebuilt from its stored published record (the record holds the whole profile)."""
    view = record.get("view")
    if not isinstance(view, Mapping):
        raise RetryDataError("a published record has no view")
    node = record.get("node") or {}
    return Agent(
        node_id=str(record["node_id"]),
        dataset_id=dataset_id,
        identity=PersonaIdentity(name=view["name"], type_label=node.get("type_label") or ""),
        role=view["role"],
        stance=Stance(view["stance"]),
        strength=view["strength"],
        confidence=view["confidence"],
        bio=view["bio"],
        details_raw=record["details_raw"],
        evidence=[EvidenceItem(**{**item, "span": tuple(item["span"])}) for item in record["evidence"]],
        relations=[RelationItem(**relation) for relation in record["relations"]],
        cites={key: list(value) for key, value in (record.get("cites") or {}).items()},
    )


def rebuild_profiles(records: Sequence[Mapping[str, Any]], dataset_id: str) -> list[Agent]:
    """The seated agents in seat order, from the published records the store returns in that order."""
    return [agent_from_record(record, dataset_id) for record in records]


def rebuild_rounds(events: Sequence[Mapping[str, Any]], retry_inputs: Mapping[str, Any]) -> list[RoundResult]:
    """The debate's rounds: each round event's turns (content, references, confidence), joined to the
    turn log for the cites and strength the events do not carry.

    The log and the events are matched by position within each round, and each pair must agree on
    speaker and stance; any disagreement is a RetryDataError, never a guess.
    """
    logged: dict[int, list[Mapping[str, Any]]] = {}
    for entry in retry_inputs.get("turns") or []:
        logged.setdefault(int(entry["round"]), []).append(entry)

    rounds: list[RoundResult] = []
    for event in events:
        if event.get("type") != "round":
            continue
        round_num = int(event["round"])
        shown = event.get("turns") or []
        kept = logged.get(round_num, [])
        if len(shown) != len(kept):
            raise RetryDataError(f"round {round_num}: {len(shown)} stored turns, {len(kept)} logged")
        turns = []
        for seen, entry in zip(shown, kept):
            if seen.get("agent_name") != entry["agent_name"] or seen.get("stance") != entry["stance"]:
                raise RetryDataError(f"round {round_num}: the turn log does not match the round events")
            turns.append(
                AgentTurn(
                    agent_id=str(seen["agent_id"]),
                    agent_name=seen["agent_name"],
                    content=seen["content"],
                    stance=seen["stance"],
                    confidence=float(seen["confidence"]),
                    strength=float(entry["strength"]),
                    references=list(seen.get("references") or []),
                    cites=tuple(entry["cites"]),
                )
            )
        rounds.append(RoundResult(round_num=round_num, turns=turns, pairs=[]))

    event_rounds = {round_result.round_num for round_result in rounds}
    if set(logged) - event_rounds:
        raise RetryDataError("the turn log names a round that has no round event")
    return rounds


def check_rebuild(
    rounds: Sequence[RoundResult],
    profiles: Sequence[Agent],
    stored: Mapping[str, Any],
    retry_inputs: Mapping[str, Any],
    query: str,
) -> None:
    """Refuse a rebuild that does not reproduce the stored board. Checked before any LLM call:

    the round count, the final stances (the seated set, by name), the consensus share and the
    position must equal what the debate stored; every turn speaker must be seated; and the rebuilt
    bundle's source numbers, citizens (name, position, cited sources) and switch lines must equal
    the fingerprint the debate stored in retry_inputs. A mismatch means the rows are not the debate's.
    """
    names = [profile.identity.name for profile in profiles]
    if len(set(names)) != len(names):
        raise RetryDataError("two seated agents share a name")
    known = set(names)
    for round_result in rounds:
        for turn in round_result.turns:
            if turn.agent_name not in known:
                raise RetryDataError("a turn speaker is not a seated agent")
    if len(rounds) != stored.get("rounds_executed"):
        raise RetryDataError("the rebuilt round count differs from the stored one")
    if board_final_stances(rounds, list(profiles)) != stored.get("final_stances"):
        raise RetryDataError("the rebuilt final stances differ from the stored ones")
    share = weighted_share(consensus_window(rounds), {p.identity.name: p for p in profiles})
    expected_share = share[1] if share is not None else 0.0
    if stored.get("weight_share") != expected_share:
        raise RetryDataError("the rebuilt weight share differs from the stored one")
    facts = board_facts(rounds, list(profiles), bool(stored.get("converged")))
    expected_position = facts.position.value if facts.position is not None else None
    if stored.get("position") != expected_position:
        raise RetryDataError("the rebuilt position differs from the stored one")
    stored_board = retry_inputs.get("board")
    if not isinstance(stored_board, Mapping):
        raise RetryDataError("the stored retry inputs carry no board fingerprint")
    rebuilt = board_fingerprint(rounds, profiles, query, str(retry_inputs.get("context") or ""))
    if canonical_board(rebuilt) != canonical_board(json_normal(stored_board)):
        raise RetryDataError("the rebuilt bundle differs from the stored one")


def canonical_board(board: Mapping[str, Any]) -> dict[str, Any]:
    """A board fingerprint with its citizens in name order: the comparison ignores how they were listed."""
    return {**board, "citizens": sorted(board["citizens"], key=lambda row: row[0])}


def json_normal(value: Any) -> Any:
    """The JSON shape of a value, so tuples and lists compare as the store returns them."""
    import json

    return json.loads(json.dumps(value))
