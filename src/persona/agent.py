"""
Canonical Agent schema.

Single source of truth for agent identity, bio, behavior, and provenance.
Consumed by every simulation stage:
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
from typing import Any, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Source evidence bounds
# ---------------------------------------------------------------------------
# How many of an agent's own source snippets are carried to its debate prompt,
# and how long each may be. One value to change, shared by the repository fetch
# (snippet cap) and the round-runner prompt (render cap + per-snippet budget).
SOURCE_EVIDENCE_MAX_SNIPPETS = 3
SOURCE_EVIDENCE_SNIPPET_CHARS = 300


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


#: The `doc_id` prefix that marks a synthesized (non-source) provenance link —
#: `PersonaRepository`'s sector fallback. A real link carries a real document id
#: and never this prefix, so a consumer that must not fabricate (the verdict's
#: `provenance_by_claim`) filters on it.
SYNTHETIC_PROVENANCE_PREFIX = "sector:"


class ConfidenceBreakdown(BaseModel):
    """Mathematical proof of the agent's groundedness."""

    source_breadth: int = Field(
        description="Number of unique documents supporting this agent"
    )
    node_density: int = Field(description="Total nodes linked to this agent")
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

    # --- 7. Source evidence (synthesis-time only; never written to the graph) ---
    source_evidence: List[str] = Field(
        default_factory=list,
        description="This agent's own source chunk snippets, rendered in its debate prompt",
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

    @field_validator(
        "domain_tags",
        "entity_affinity",
        "instinct_tags",
        "expertise_areas",
        mode="before",
    )
    @classmethod
    def _coerce_tag_list(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        if isinstance(v, (list, tuple)):
            return [str(t).strip() for t in v if str(t).strip()]
        return []
