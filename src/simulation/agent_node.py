"""
AgentNode: Core agent persona model for simulation.
Exposes BCO framework and CIOR metrics for agent behavior.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Stance(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    AMBIVALENT = "AMBIVALENT"


class AgentNode(BaseModel):
    """
    Agent persona model for the simulation framework.

    Contains all properties needed to define agent behavior including:
    - Identity: Core identifying information
    - Response: Stance and intensity parameters
    - BCO: Belief-Conviction-Opinion framework
    - CIOR: Certainty-Instinct Opinion Range with instinct tags
    - Communication: Domain and entity boundaries
    - Visibility: UI display properties
    - Dynamic: Runtime state updated per simulation tick
    """

    # --- Identity ---
    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    name: str = Field(description="Human-readable agent name")
    archetype: str = Field(description="Domain category (e.g., MARKET_ANALYST, REGULATORY_BODY)")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # --- Response Parameters ---
    stance: Stance = Field(default=Stance.NEUTRAL)
    intensity: float = Field(ge=0.0, le=1.0, default=0.5, description="Response intensity")
    confidence: float = Field(ge=0.0, le=1.0, default=0.5, description="Computed from graph connectivity")

    # --- BCO Framework ---
    belief: str = Field(default="", description="Agent's world model")
    conviction: float = Field(ge=0.0, le=1.0, default=0.5, description="How unshakeable the belief")
    opinion: str = Field(default="", description="Specific take on current query")

    # --- CIOR Framework ---
    cior: float = Field(
        ge=-1.0, le=1.0, default=0.0,
        description="Certainty-Instinct Opinion Range (-1.0 to 1.0)"
    )
    instinct_tags: List[str] = Field(
        default_factory=list,
        description="Behavioral instinct tags (e.g., risk_averse, growth_seeker)"
    )

    # --- Communication Boundary ---
    domain_tags: List[str] = Field(
        default_factory=list,
        description="Which query domains this agent responds to"
    )
    entity_affinity: List[str] = Field(
        default_factory=list,
        description="Which entity types this agent connects to"
    )
    communication_radius: int = Field(
        ge=0, default=1,
        description="Graph hop radius for communication reach"
    )

    # --- Visibility ---
    role_description: str = Field(
        default="",
        description="Human-readable description of agent role"
    )
    expertise_areas: List[str] = Field(
        default_factory=list,
        description="Areas of expertise for UI display"
    )
    display_order: int = Field(default=0, description="UI sorting order")

    # --- Dynamic Fields ---
    last_query: str = Field(default="", description="Most recent query processed")
    last_response: str = Field(default="", description="Most recent response generated")
    activation_count: int = Field(default=0, ge=0, description="Number of times activated in simulation")

    @field_validator("updated_at", mode="before")
    @classmethod
    def _update_timestamp(cls, v: datetime | None) -> datetime:
        return v or datetime.utcnow()

    model_config = ConfigDict(use_enum_values=True)
