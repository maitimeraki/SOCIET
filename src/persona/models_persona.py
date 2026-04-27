from dataclasses import dataclass, field
from typing import List, Dict


from pydantic import BaseModel, Field, HttpUrl
from typing import List, Dict, Optional, Any
from uuid import UUID, uuid4
from datetime import datetime
from enum import Enum

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
    archetype: str = Field(description="It could be a role like 'The Visionary', 'The Analyst', or 'The Connector' that takes from graph's type_name")
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
    source_breadth: int = Field(description="Number of unique documents supporting this persona")
    node_density: int = Field(description="Total number of nodes linked to this agent")
    relationship_connectivity: float = Field(description="Graph centrality score of the agent's cluster")

class ProvenanceLink(BaseModel):
    """Traceability back to the original source text."""
    doc_id: str
    title: str
    breadcrumb: str
    chunk_id: UUID

# --- The Root Agent Model ---

class AgentProfile(BaseModel):
    """The complete, production-grade Agent Profile for Simulation."""
    
    # 1. Identity & System Metadata
    agent_id: UUID = Field(default_factory=uuid4)
    discovery_type: DiscoveryType
    expertise_level: ExpertiseLevel
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    # version_hash: str = Field(description="Hash of the graph state at time of synthesis")

    # 2. Persona Definition (From your Dataclasses)
    identity: PersonaIdentity
    # biases: List[PersonaBias] = Field(default_factory=list)
    # memories: List[PersonaMemory] = Field(default_factory=list)

    # 3. GraphRAG Enrichment (The 'White-Box' logic)
    # primary_sector: str 
    domain_tags: List[str]
    # core_entities: List[str] = Field(description="Key Neo4j nodes this agent represents")
    
    # 4. Perspective & Summarization
    description: str = Field(description="High-level role summary for UI cards")
    detailed_perspective: str = Field(description="Synthesized first-person worldview")

    # 5. Reliability Metrics
    confidence: float = Field(ge=-1, le=1)
    confidence_breakdown: ConfidenceBreakdown
    provenance: List[ProvenanceLink]

        
    # def to_prompt_dict(self) -> Dict:
    #     return {
    #         "org_name": self.identity.name,
    #         "archetype": self.identity.archetype,
    #         "communication_style": self.identity.communication_style,
    #         "core_values": ", ".join(self.identity.core_values) if self.identity.core_values else "Not specified",
    #         "culture": self.identity.culture or "Not specified",
    #         "mission": self.identity.mission or "Not specified",
    #         "recent_history": [
    #             f"{m.relation_type} {m.target_name}" if not m.summary else f"{m.relation_type} {m.target_name} ({m.summary})"
    #             for m in self.memories
    #         ],
    #         "bias_instructions": [b.instruction for b in self.biases],
    #     }