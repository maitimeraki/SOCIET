"""PairTurn types shared across simulation modules."""
from dataclasses import dataclass, field
from typing import Dict, List

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
    """Single agent turn in the debate."""
    agent_id: str
    agent_name: str
    content: str
    stance: str
    confidence: float
    references: List[str] = field(default_factory=list)
    #: The agent's private REASONING section — grounding material for synthesis,
    #: never the stated position (that is `content`).
    reasoning: str = ""


@dataclass
class RoundResult:
    """Result of a single debate round."""
    round_num: int
    turns: List[AgentTurn]
    pairs: List[CommPair]


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
    """Final verdict with weighted synthesis."""
    overall_stance: Stance
    confidence_score: float
    supporting_entities: List[str]
    opposing_entities: List[str]
    summary: str
    cluster_details: Dict[Stance, ClusterSummary]
    provenance_by_claim: Dict[str, List[ProvenanceLink]] = field(default_factory=dict)
    rounds_executed: int = 0
    #: The dominant stance's share of total weight — the honest name for the
    #: number `confidence_score` has always carried.
    weight_share: float = 0.0
    #: True when the dominant share is below the contested threshold (near-tie).
    contested: bool = False
    #: Markdown answer assembled from the structured verdict (query-grounded).
    #: Empty when synthesis fell back to `summary`.
    narrative: str = ""
    #: "ok" when `narrative` is the query-grounded answer; "fallback" when it
    #: degraded to `summary` (no client, or the answer-writer produced no
    #: parseable JSON after bounded retries). Never silent.
    narrative_status: str = "ok"
    #: Per-cluster dissent rendered from the structured verdict.
    dissenting_views: List[dict] = field(default_factory=list)
    #: Cited entities/claims backing the answer.
    evidence: List[dict] = field(default_factory=list)
