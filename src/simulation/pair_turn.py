"""PairTurn types extracted from graph_debate_engine for shared use across modules."""
from dataclasses import dataclass, field
from typing import Dict, List

from src.simulation.agent_node import Stance
from src.simulation.communication_graph import CommPair
from src.persona.models_persona import ProvenanceLink


@dataclass
class AgentTurn:
    """Single agent turn in the debate."""
    agent_id: str
    agent_name: str
    content: str
    stance: str
    confidence: float
    references: List[str] = field(default_factory=list)


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
