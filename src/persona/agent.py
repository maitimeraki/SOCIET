"""
Canonical Agent schema (spec 4a, 5).

One definition per concept: the stance enum with its single parser, the identity,
and the slim Agent that the profile synthesizer seats and every simulation stage
reads. The client-safe projection is `Agent.view()` (AgentView).
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Dict, List
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.simulation.evidence import EvidenceItem, RelationItem
from src.simulation.profile_validation import strip_markers

if TYPE_CHECKING:
    from src.simulation.agent_record import AgentView


class Stance(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    ABSTAIN = "ABSTAIN"

    @classmethod
    def parse(cls, value: object) -> "Stance":
        """The single stance parser. Raises ValueError on anything but a known stance."""
        if not isinstance(value, str):
            raise ValueError(f"not a stance: {value!r}")
        return cls(value.strip().upper())


#: The stances a turn can carry on the wire and in weight dicts.
WIRE_STANCES: tuple[Stance, ...] = (
    Stance.POSITIVE,
    Stance.NEGATIVE,
    Stance.NEUTRAL,
    Stance.ABSTAIN,
)


class PersonaIdentity(BaseModel):
    """The agent's identity: the graph entity's name and its real type."""

    name: str
    type_label: str = ""  # the graph entity's real type; "" when the graph carries none


class Agent(BaseModel):
    """A seated debate participant, derived from one graph entity and its evidence."""

    model_config = ConfigDict(extra="ignore")

    agent_id: UUID = Field(default_factory=uuid4)
    node_id: str
    dataset_id: str
    identity: PersonaIdentity
    role: str
    stance: Stance
    strength: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    bio: str
    details_raw: str
    evidence: List[EvidenceItem]
    relations: List[RelationItem]
    cites: Dict[str, List[str]]

    @property
    def details(self) -> str:
        """The profile prose with citation markers stripped; the only form a client sees."""
        return strip_markers(self.details_raw)

    def view(self) -> "AgentView":
        """The client-safe projection (spec 4a). Local import: agent_record imports this module."""
        from src.simulation.agent_record import AgentView

        return AgentView(
            name=self.identity.name,
            type=self.identity.type_label or "type unknown",
            role=self.role,
            stance=self.stance,
            strength=self.strength,
            bio=strip_markers(self.bio),
            details=self.details,
            confidence=self.confidence,
        )
