"""
Canonical Agent schema.

Single source of truth for agent identity, bio, behavior, and provenance.
Replaces the fragmented AgentProfile (persona/models_persona.py) model —
verdict, round runner, topology, orchestrator, and society memory all consume
this model.

Field layout follows the user's "production-grade bio file" requirement:
  - Identity: name, archetype, communication_style
  - Bio: bio (narrative), detailed_perspective (first-person voice),
         role_description (one-liner)
  - Stance & confidence: stance, intensity, confidence, conviction,
                          belief, opinion, cior
  - Tags & reach: domain_tags, entity_affinity, instinct_tags,
                  expertise_areas, communication_radius
  - Provenance: summary_provenance (chunk links), confidence_breakdown
                (mathematical proof), graph_snapshot (tenant/version info)
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Stance(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    AMBIVALENT = "AMBIVALENT"


class DiscoveryType(str, Enum):
    INTENT_DRIVEN = "intent_driven"
    GRAPH_DISCOVERY = "graph_discovery"


class ExpertiseLevel(str, Enum):
    STRATEGIC = "Strategic"
    TECHNICAL = "Technical"
    OPERATIONAL = "Operational"


# ---------------------------------------------------------------------------
# Component models
# ---------------------------------------------------------------------------


class PersonaIdentity(BaseModel):
    """Static 'soul' of the agent."""

    name: str
    archetype: str = Field(
        description="Role label (e.g. 'The Visionary', 'REGULATORY_BODY')"
    )
    communication_style: str


class ProvenanceLink(BaseModel):
    """Traceability back to the original source chunk."""

    doc_id: str
    title: str
    breadcrumb: str = ""
    chunk_id: UUID


class ConfidenceBreakdown(BaseModel):
    """Mathematical proof of the agent's groundedness."""

    source_breadth: int = Field(
        description="Number of unique documents supporting this agent"
    )
    node_density: int = Field(
        description="Total nodes linked to this agent"
    )
    relationship_connectivity: float = Field(
        description="Graph centrality score of the agent's cluster"
    )


class GraphSnapshot(BaseModel):
    """Snapshot of the graph state at the moment of synthesis.

    Embedded into every Agent so downstream consumers can reason about
    staleness without an extra round-trip to Neo4j.
    """

    dataset_id: str
    ontology_id: Optional[str] = None
    chunk_count: int = 0
    version_hash: str = Field(
        default_factory=lambda: uuid4().hex,
        description="Hash of graph state at synthesis time (auditability)",
    )


# ---------------------------------------------------------------------------
# The canonical Agent
# ---------------------------------------------------------------------------


class Agent(BaseModel):
    """The complete, production-grade agent model.

    Every field the downstream pipeline reads lives here. The verdict
    synthesizer's CIOR weights, the round runner's prompt construction,
    the topology's pair scoring, and the society memory's persistence all
    consume Agent fields — and previously each file looked at a
    different schema. There is now exactly one.
    """

    model_config = ConfigDict(extra="ignore")

    # --- 1. Identity & system metadata ---
    agent_id: UUID = Field(default_factory=uuid4)
    identity: PersonaIdentity
    discovery_type: DiscoveryType
    expertise_level: ExpertiseLevel = ExpertiseLevel.STRATEGIC
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    # --- 2. Bio (the user's explicit ask) ---
    bio: str = Field(
        default="",
        description="2-3 sentence narrative bio, LLM-generated from graph evidence",
    )
    detailed_perspective: str = Field(
        default="",
        description="First-person voice used in debate prompts",
    )
    role_description: str = Field(
        default="",
        description="One-line role summary for UI cards",
    )

    # --- 3. Stance & confidence (behavioral core) ---
    stance: Stance = Stance.NEUTRAL
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    conviction: float = Field(default=0.5, ge=0.0, le=1.0)
    belief: str = Field(default="", description="Agent's world model")
    opinion: str = Field(default="", description="Specific take on the current query")
    cior: float = Field(
        default=0.0,
        ge=-1.0,
        le=1.0,
        description="Certainty-Instinct Opinion Range (-1 hostile → +1 receptive)",
    )

    # --- 4. Tags & reach ---
    instinct_tags: List[str] = Field(default_factory=list)
    domain_tags: List[str] = Field(default_factory=list)
    entity_affinity: List[str] = Field(default_factory=list)
    expertise_areas: List[str] = Field(default_factory=list)
    communication_radius: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Graph-hop radius used by CommunicationTopology",
    )

    # --- 5. Provenance (white-box traceability) ---
    summary_provenance: List[ProvenanceLink] = Field(default_factory=list)
    confidence_breakdown: ConfidenceBreakdown = Field(
        default_factory=lambda: ConfidenceBreakdown(
            source_breadth=0, node_density=0, relationship_connectivity=0.0
        )
    )

    # --- 6. Graph snapshot (auditability) ---
    graph_snapshot: GraphSnapshot = Field(
        default_factory=lambda: GraphSnapshot(dataset_id="unknown")
    )

    # --- validators ---
    @field_validator("stance", mode="before")
    @classmethod
    def _coerce_stance(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return Stance(v.upper())
            except ValueError:
                return Stance.NEUTRAL
        return v

    @field_validator("domain_tags", "entity_affinity", "instinct_tags", "expertise_areas", mode="before")
    @classmethod
    def _coerce_tag_list(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        if isinstance(v, (list, tuple)):
            return [str(t).strip() for t in v if str(t).strip()]
        return []


# ---------------------------------------------------------------------------
# Backwards-compatible aliases
# ---------------------------------------------------------------------------
# Older imports (`from src.persona.models_persona import AgentProfile`)
# keep working for one release. New code MUST import Agent from this module.
# ---------------------------------------------------------------------------

from src.persona.models_persona import (  # noqa: E402  (intentional late import)
    AgentProfile as _AgentProfileShim,
    ConfidenceBreakdown as _ConfidenceBreakdownShim,
    PersonaIdentity as _PersonaIdentityShim,
    ProvenanceLink as _ProvenanceLinkShim,
    DiscoveryType as _DiscoveryTypeShim,
    ExpertiseLevel as _ExpertiseLevelShim,
)


def agent_profile_to_agent(profile: _AgentProfileShim, dataset_id: str) -> Agent:
    """Convert a legacy AgentProfile to the canonical Agent.

    Missing behavioral fields (stance, conviction, cior, etc.) are filled
    with safe defaults so the verdict synthesizer stops silently falling
    back to 0.5/0.0 on every profile.
    """

    # Pydantic v2: nested model fields need model_validate when given as
    # model instances from a sibling class hierarchy.
    identity_obj = profile.identity
    if isinstance(identity_obj, PersonaIdentity):
        identity_data = identity_obj.model_dump()
    else:
        identity_data = dict(identity_obj) if not isinstance(identity_obj, dict) else identity_obj
    identity = PersonaIdentity.model_validate(identity_data)

    cb_obj = profile.confidence_breakdown
    if isinstance(cb_obj, ConfidenceBreakdown):
        cb_data = cb_obj.model_dump()
    else:
        cb_data = dict(cb_obj) if not isinstance(cb_obj, dict) else cb_obj
    cb = ConfidenceBreakdown.model_validate(cb_data)

    return Agent(
        agent_id=profile.agent_id,
        identity=identity,
        discovery_type=profile.discovery_type,
        expertise_level=profile.expertise_level,
        last_updated=profile.last_updated,
        bio=profile.description,
        detailed_perspective=profile.detailed_perspective,
        role_description="",
        stance=Stance.NEUTRAL,
        intensity=0.5,
        confidence=float(profile.confidence),
        conviction=0.5,
        belief="",
        opinion="",
        cior=0.0,
        domain_tags=list(profile.domain_tags),
        summary_provenance=list(profile.provenance),
        confidence_breakdown=cb,
        graph_snapshot=GraphSnapshot(dataset_id=dataset_id),
    )
