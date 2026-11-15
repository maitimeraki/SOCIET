"""The declared-POSITION turn protocol: parse one agent turn and apply the position-change rule.

A turn is four labelled sections, one label per line, in this order:

    REASONING: <private thinking, parsed and dropped>
    POSITION: <POSITIVE|NEGATIVE|NEUTRAL|ABSTAIN> <strength 0-1>
    CITES: <evidence ids, comma separated; empty for none>
    ANSWER: <the reply, to the end of the text>

Labels match at line starts. Only the first POSITION line before ANSWER counts;
anything after ANSWER is answer text, so the reply cannot spoof a stance. Every
deviation raises ValueError with a fixed message, so a warning can name the class
of failure without echoing model text.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from src.persona.agent import WIRE_STANCES, Agent, Stance
from src.simulation.pair_turn import AgentTurn, RoundResult

#: Stated once; the retry prompt restates the same text through _format_instruction.
KEPT_NO_NEW_CITE = "kept: no new cite"

_LABEL = re.compile(r"^\s*(REASONING|POSITION|CITES|ANSWER):(.*)$")
_BEFORE_ANSWER = ("REASONING", "POSITION", "CITES")

_NO_REASONING = "no REASONING line"
_NO_POSITION = "no valid POSITION line"
_NO_CITES = "no valid CITES line"
_NO_ANSWER = "no ANSWER line"
_EMPTY_ANSWER = "empty ANSWER"
_DUPLICATE = "duplicated section before ANSWER"
_ORDER = "sections out of order before ANSWER"
_STRAY = "text outside a labelled section"
_UNKNOWN_STANCE = "unknown stance word"
_STRENGTH = "strength is not a number in [0, 1]"
_CITE = "cite outside the agent's evidence"


@dataclass(frozen=True)
class TurnParse:
    position: Stance
    strength: float
    cites: tuple[str, ...]
    answer: str


@dataclass
class PositionState:
    """An agent's held stance, and every evidence id it has cited in a valid turn."""

    stance: Stance
    cites_used: set[str] = field(default_factory=set)


def parse_turn(text: str, own_ids: set[str]) -> TurnParse:
    """Parse one turn's declared form. Raises ValueError on any deviation; REASONING is dropped."""
    seen: list[str] = []
    values: dict[str, str] = {}
    answer_lines: list[str] | None = None
    current: str | None = None
    for line in text.splitlines():
        if answer_lines is not None:
            answer_lines.append(line)
            continue
        match = _LABEL.match(line)
        if match is None:
            if line.strip() and current != "REASONING":
                raise ValueError(_STRAY)
            continue
        label, rest = match.group(1), match.group(2).strip()
        current = label
        if label == "ANSWER":
            answer_lines = [rest]
            continue
        if label in seen:
            raise ValueError(_DUPLICATE)
        seen.append(label)
        values[label] = rest

    if answer_lines is None:
        raise ValueError(_NO_ANSWER)
    if "REASONING" not in seen:
        raise ValueError(_NO_REASONING)
    if "POSITION" not in seen:
        raise ValueError(_NO_POSITION)
    if "CITES" not in seen:
        raise ValueError(_NO_CITES)
    if seen != list(_BEFORE_ANSWER):
        raise ValueError(_ORDER)

    parts = values["POSITION"].split()
    if len(parts) != 2:
        raise ValueError(_NO_POSITION)
    try:
        position = Stance.parse(parts[0])
    except ValueError:
        raise ValueError(_UNKNOWN_STANCE) from None
    try:
        strength = float(parts[1])
    except ValueError:
        raise ValueError(_STRENGTH) from None
    if not math.isfinite(strength) or not 0.0 <= strength <= 1.0:
        raise ValueError(_STRENGTH)

    raw_cites = values["CITES"]
    cites = tuple(part.strip() for part in raw_cites.split(",")) if raw_cites else ()
    if any(cite not in own_ids for cite in cites):
        raise ValueError(_CITE)

    answer = "\n".join(answer_lines).strip()
    if not answer:
        raise ValueError(_EMPTY_ANSWER)
    return TurnParse(position=position, strength=strength, cites=cites, answer=answer)


def accept_position(
    previous: PositionState | None, parse: TurnParse
) -> tuple[Stance, str]:
    """The stance an agent holds after this turn, and the reason it differs from the declared one.

    The first declared position is taken as given, and so is a repeat of the held stance. A
    change of stance, to or from ABSTAIN included, needs at least one cite the agent has not used
    before. Without one the held stance stands and the reason says so.
    """
    if previous is None or parse.position is previous.stance:
        return parse.position, ""
    if any(cite not in previous.cites_used for cite in parse.cites):
        return parse.position, ""
    return previous.stance, KEPT_NO_NEW_CITE


#: The stances that can carry weight: a position a turn takes. ABSTAIN is not one.
POSITION_STANCES: tuple[Stance, ...] = tuple(s for s in WIRE_STANCES if s is not Stance.ABSTAIN)

#: How many rounds the consensus reads: the stop test's window, and the verdict's.
CONSENSUS_ROUNDS = 2


def consensus_window(rounds: Sequence[RoundResult]) -> list[AgentTurn]:
    """The turns the consensus reads: the last CONSENSUS_ROUNDS rounds."""
    return [turn for round_result in rounds[-CONSENSUS_ROUNDS:] for turn in round_result.turns]


def consensus_round_count(rounds: Sequence[RoundResult]) -> int:
    """How many rounds the consensus window covers: min(CONSENSUS_ROUNDS, rounds run so far)."""
    return min(CONSENSUS_ROUNDS, len(rounds))


def dominant_stance(weights: Mapping[Stance, float]) -> Stance | None:
    """The position stance with the largest weight, or None when no position carries weight.

    The one tie-break: a tie goes to the first stance in POSITION_STANCES order
    (POSITIVE, then NEGATIVE, then NEUTRAL). Every consumer of a dominant stance goes through here.
    """
    best: Stance | None = None
    best_weight = 0.0
    for stance in POSITION_STANCES:
        weight = weights.get(stance, 0.0)
        if weight > best_weight:
            best, best_weight = stance, weight
    return best


def _unit(value: float, field_name: str, speaker: str) -> float:
    """A strength or confidence as a float in [0, 1]; anything else is a ValueError, never clamped."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} of {speaker!r} is not a number")
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{field_name} of {speaker!r} is outside [0, 1]")
    return float(value)


def stance_weights(turns: Iterable[AgentTurn], profiles: Mapping[str, Agent]) -> dict[Stance, float]:
    """Weight per wire stance: the sum over the turns taking it of strength x profile confidence.

    Every turn's speaker must be in `profiles`, else ValueError: a missing profile is a
    broken run, not a 0.5 default. ABSTAIN weighs 0. The sums are exact (math.fsum), so the
    weights do not depend on the order of the turns.
    """
    parts: dict[Stance, list[float]] = {stance: [] for stance in WIRE_STANCES}
    for turn in turns:
        profile = profiles.get(turn.agent_name)
        if profile is None:
            raise ValueError(f"no profile for turn speaker {turn.agent_name!r}")
        strength = _unit(turn.strength, "strength", turn.agent_name)
        confidence = _unit(profile.confidence, "confidence", turn.agent_name)
        stance = Stance.parse(turn.stance)
        if stance is not Stance.ABSTAIN:
            parts[stance].append(strength * confidence)
    return {stance: math.fsum(values) for stance, values in parts.items()}


def weighted_share(
    turns: Sequence[AgentTurn], profiles: Mapping[str, Agent]
) -> tuple[Stance, float] | None:
    """The one consensus number: the dominant position's share of the counted weight.

    Weight is strength x profile confidence; ABSTAIN contributes nothing. Returns None when no
    turn takes a position or the counted weight is zero: that is no verdict, never NEUTRAL.
    The dominant stance is chosen by dominant_stance (ties: POSITIVE, then NEGATIVE, then NEUTRAL).
    """
    weights = stance_weights(turns, profiles)
    dominant = dominant_stance(weights)
    if dominant is None:
        return None
    total = math.fsum(weights[stance] for stance in POSITION_STANCES)
    return dominant, weights[dominant] / total
