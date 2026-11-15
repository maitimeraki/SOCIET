"""Agent view and per-run agent record (spec §4a, §5).

BACKEND-ONLY: AgentRecord must never be serialised to a client or imported from
src/api. The client sees AgentView alone (spec §4a, §4b).
"""

import hashlib
import json
from dataclasses import asdict
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.persona.agent import Stance
from src.simulation import ranking
from src.simulation.evidence import EvidenceItem, EvidencePack, RelationItem
from src.simulation.profile_generator import PROFILE_PROMPT_VERSION

_STRICT = ConfigDict(extra="forbid")


class AgentView(BaseModel):
    model_config = _STRICT

    name: str
    type: str
    role: str
    stance: Stance
    strength: float = Field(ge=0.0, le=1.0)
    bio: str
    details: str
    confidence: float = Field(ge=0.0, le=1.0)


class NodeInfo(BaseModel):
    model_config = _STRICT

    name: str
    aliases: list[str]
    type_label: Optional[str]
    type_source: Literal["graph", "unknown"]


class RankInfo(BaseModel):
    model_config = _STRICT

    features: dict[str, float]
    score: float
    seated: bool
    reason: str
    order: Optional[int]


class RejectedClaim(BaseModel):
    model_config = _STRICT

    field: str
    reason: str


class ValidationInfo(BaseModel):
    model_config = _STRICT

    json_ok: bool
    repairs: int = Field(ge=0)
    rejected: list[RejectedClaim]
    details_chars: int = Field(ge=0)
    cites_valid: bool


class UniquenessInfo(BaseModel):
    model_config = _STRICT

    max_bio_sim: Optional[float] = None
    max_details_sim: Optional[float] = None
    max_cite_overlap: Optional[float] = None
    pair: Optional[list[str]] = None


class CiteIds(BaseModel):
    model_config = _STRICT

    role: list[str] = Field(default_factory=list)
    stance: list[str] = Field(default_factory=list)
    bio: list[str] = Field(default_factory=list)
    details: list[str] = Field(default_factory=list)
    confidence: list[str] = Field(default_factory=list)


class GenerationInfo(BaseModel):
    model_config = _STRICT

    model: str
    prompt_version: str
    temperature: float
    attempts: int = Field(ge=1)
    latency_ms: int = Field(ge=0)


class AgentRecord(BaseModel):
    model_config = _STRICT

    run_id: str
    node_id: str
    query_hash: str
    question: str
    decision_axis: str
    node: NodeInfo
    rank: RankInfo
    evidence: list[EvidenceItem]
    relations: list[RelationItem]
    view: Optional[AgentView]  # None when the candidate was not seated: no text is invented
    details_raw: str
    cites: CiteIds
    validation: ValidationInfo
    uniqueness: UniquenessInfo
    generation: GenerationInfo
    dossier_hash: str
    status: Literal["published", "rejected", "stale"]
    reason: Optional[str] = None


def dossier_hash(pack: EvidencePack, config: object) -> str:
    payload = {
        "items": [[item.id, list(item.span), item.text] for item in pack.items],
        "relations": [asdict(relation) for relation in pack.relations],
        "config": str(config),
        "prompt_version": PROFILE_PROMPT_VERSION,
        "ranking": {
            "RRF_K": ranking.RRF_K,
            "PPR_ALPHA": ranking.PPR_ALPHA,
            "W_QUERY": ranking.W_QUERY,
            "W_ENTITY": ranking.W_ENTITY,
            "W_PPR": ranking.W_PPR,
            "MMR_LAMBDA": ranking.MMR_LAMBDA,
            "MIN_EVIDENCE": ranking.MIN_EVIDENCE,
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
