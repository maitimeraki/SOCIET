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
from dataclasses import dataclass, field

from src.persona.agent import Stance

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
