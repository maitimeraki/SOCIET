from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

# --- Supporting Enums ---


class DiscoveryType(str, Enum):
    INTENT_DRIVEN = "intent_driven"
    GRAPH_DISCOVERY = "graph_discovery"


class ExpertiseLevel(str, Enum):
    STRATEGIC = "Strategic"
    TECHNICAL = "Technical"
    OPERATIONAL = "Operational"


# --- Component Models ---

# class PersonaMemory(BaseModel):
#     """Represents a relational edge from the graph used as a specific memory."""
#     relation_type: str
#     target_name: str
#     summary: str
#     timestamp: Optional[datetime] = None


class PersonaIdentity(BaseModel):
    """The static 'soul' of the agent."""

    name: str
    archetype: str = Field(
        description="It could be a role like 'The Visionary', 'The Analyst', or 'The Connector' that takes from graph's type_name"
    )
    communication_style: str
    # core_values: List[str] = Field(default_factory=list)
    # culture: str = ""
    # mission: str = ""


# class PersonaBias(BaseModel):
#     """Dictates how the agent reacts to specific entities or sectors in a debate."""
#     target: str
#     relationship: str
#     instruction: str
#     weight: float = Field(default=0.6, ge=0, le=1)


class ConfidenceBreakdown(BaseModel):
    """Mathematical proof of the agent's groundedness."""

    source_breadth: int = Field(
        description="Number of unique documents supporting this persona"
    )
    node_density: int = Field(description="Total number of nodes linked to this agent")
    relationship_connectivity: float = Field(
        description="Graph centrality score of the agent's cluster"
    )


class ProvenanceLink(BaseModel):
    """Traceability back to the original source text."""

    doc_id: str
    title: str
    breadcrumb: str
    chunk_id: UUID
