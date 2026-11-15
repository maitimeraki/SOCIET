"""PairTurn types shared across simulation modules."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from src.persona.agent import Stance
from src.persona.models_persona import ProvenanceLink


@dataclass
class CommPair:
    """A communication pair between two agents (uses agent names)."""

    agent_a: str  # agent name
    agent_b: str  # agent name
    shared_entities: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    score: float = 0.0  # topology-derived pair quality score


@dataclass
class ActivationCandidate:
    """A non-participating agent that should join the debate."""

    agent_name: str
    shared_entities: List[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class AgentTurn:
    """Single agent turn in the debate. REASONING is parsed and dropped, never stored here."""

    agent_id: str
    agent_name: str
    #: The ANSWER section: the stated reply.
    content: str
    #: The held stance after the position-change rule, in wire casing.
    stance: str
    #: The speaker's profile confidence.
    confidence: float
    #: The declared POSITION strength, in [0, 1].
    strength: float
    references: List[str] = field(default_factory=list)
    #: Evidence ids the turn cites; they stay server-side (never on the wire).
    cites: Tuple[str, ...] = ()
    #: "" when the declared position was taken, else why the held stance stood.
    position_reason: str = ""


@dataclass
class RoundResult:
    """Result of a single debate round."""

    round_num: int
    turns: List[AgentTurn]
    pairs: List[CommPair]
    #: Warnings from this round, each naming an agent and a class of failure.
    warnings: List[str] = field(default_factory=list)


@dataclass
class DebateResult:
    """Final result of a complete debate."""

    query: str
    rounds: List[RoundResult]
    converged: bool
    final_stances: Dict[str, str]
    verdict: str
    warnings: List[str] = field(default_factory=list)


@dataclass
class ClusterSummary:
    """Summary of an opinion cluster."""

    stance: Stance
    count: int
    total_weight: float
    avg_confidence: float
    avg_conviction: float
    agents: List[str]


@dataclass
class DebateVerdict:
    """Final verdict: the consensus numbers over the window, and the final report's stored fields."""

    overall_stance: Stance
    confidence_score: float
    supporting_entities: List[str]
    opposing_entities: List[str]
    cluster_details: Dict[Stance, ClusterSummary]
    provenance_by_claim: Dict[str, List[ProvenanceLink]] = field(default_factory=dict)
    rounds_executed: int = 0
    #: The dominant stance's share of total weight — the honest name for the
    #: number `confidence_score` has always carried.
    weight_share: float = 0.0
    #: True when the dominant share is below the contested threshold (near-tie).
    contested: bool = False
    #: The stored report fields (title, markdown, position, sources, source_refs, attempts,
    #: checks, status); see verdict.write_board_report. Empty until the report is written.
    report: Dict[str, Any] = field(default_factory=dict)
