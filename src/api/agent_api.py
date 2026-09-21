"""
Agent API: FastAPI router for agent CRUD operations.
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict

from src.graph.config_graph import GraphConfig
from src.persona.agent_repository import AgentRepository
from src.persona.response_tracker import ResponseTracker, AgentTurn
from src.simulation.agent_node import AgentNode, Stance
from src.logging.setup_logging import setup_logging

router = APIRouter(prefix="/api/agents", tags=["agents"])
logger = setup_logging()


class AgentUpdateRequest(BaseModel):
    """Fields that can be updated on an agent."""
    name: Optional[str] = None
    stance: Optional[Stance] = None
    intensity: Optional[float] = Field(None, ge=0.0, le=1.0)
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    belief: Optional[str] = None
    conviction: Optional[float] = Field(None, ge=0.0, le=1.0)
    opinion: Optional[str] = None
    cior: Optional[float] = Field(None, ge=-1.0, le=1.0)
    instinct_tags: Optional[List[str]] = None
    domain_tags: Optional[List[str]] = None
    entity_affinity: Optional[List[str]] = None
    communication_radius: Optional[int] = Field(None, ge=0)
    role_description: Optional[str] = None
    expertise_areas: Optional[List[str]] = None
    display_order: Optional[int] = None


class AgentListResponse(BaseModel):
    agents: List[Dict[str, Any]]
    total: int


class AgentResponse(BaseModel):
    agent: Dict[str, Any]


class AgentHistoryResponse(BaseModel):
    history: List[Dict[str, Any]]


def _agent_to_dict(agent: AgentNode) -> Dict[str, Any]:
    """Convert AgentNode to dict for JSON serialization."""
    # stance is already string due to use_enum_values=True in AgentNode
    stance_val = agent.stance
    if hasattr(stance_val, "value"):
        stance_val = stance_val.value

    return {
        "id": str(agent.id),
        "name": agent.name,
        "archetype": agent.archetype,
        "created_at": agent.created_at.isoformat(),
        "updated_at": agent.updated_at.isoformat(),
        "stance": stance_val,
        "intensity": agent.intensity,
        "confidence": agent.confidence,
        "belief": agent.belief,
        "conviction": agent.conviction,
        "opinion": agent.opinion,
        "cior": agent.cior,
        "instinct_tags": agent.instinct_tags,
        "domain_tags": agent.domain_tags,
        "entity_affinity": agent.entity_affinity,
        "communication_radius": agent.communication_radius,
        "role_description": agent.role_description,
        "expertise_areas": agent.expertise_areas,
        "display_order": agent.display_order,
        "last_query": agent.last_query,
        "last_response": agent.last_response,
        "activation_count": agent.activation_count,
    }


def _turn_to_dict(turn: AgentTurn) -> Dict[str, Any]:
    """Convert AgentTurn to dict for JSON serialization."""
    return {
        "agent_id": turn.agent_id,
        "query": turn.query,
        "response": turn.response,
        "timestamp": turn.timestamp.isoformat(),
        "stance": turn.stance.value if hasattr(turn.stance, "value") else turn.stance,
        "confidence": turn.confidence,
        "round": turn.round,
    }


@router.get("", response_model=AgentListResponse)
async def list_agents(
    archetype: Optional[str] = None,
    stance: Optional[str] = None,
    domain_tags: Optional[str] = None,
    min_confidence: Optional[float] = None,
    limit: int = 100,
    offset: int = 0,
):
    """List all agents with optional filtering."""
    cfg = GraphConfig()
    repo = AgentRepository(cfg)
    try:
        filters = {"limit": limit, "offset": offset}
        if archetype:
            filters["archetype"] = archetype
        if stance:
            filters["stance"] = stance
        if domain_tags:
            filters["domain_tags"] = domain_tags
        if min_confidence is not None:
            filters["min_confidence"] = min_confidence

        agents = await repo.list_agents(filters)
        return AgentListResponse(
            agents=[_agent_to_dict(a) for a in agents],
            total=len(agents),
        )
    finally:
        await repo.close()


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str):
    """Get a specific agent by ID."""
    cfg = GraphConfig()
    repo = AgentRepository(cfg)
    try:
        agent = await repo.get_agent(agent_id)
        if agent is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )
        return AgentResponse(agent=_agent_to_dict(agent))
    finally:
        await repo.close()


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(agent_id: str, updates: AgentUpdateRequest):
    """Update agent persona fields."""
    cfg = GraphConfig()
    repo = AgentRepository(cfg)
    try:
        # Check if agent exists
        existing = await repo.get_agent(agent_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )

        # Build updates dict from non-None fields
        update_dict: Dict[str, Any] = {}
        for field_name, value in updates.model_dump(exclude_none=True).items():
            if value is not None:
                update_dict[field_name] = value

        if not update_dict:
            return AgentResponse(agent=_agent_to_dict(existing))

        updated = await repo.update_agent(agent_id, update_dict)
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found after update",
            )
        return AgentResponse(agent=_agent_to_dict(updated))
    finally:
        await repo.close()


@router.get("/{agent_id}/history", response_model=AgentHistoryResponse)
async def get_agent_history(agent_id: str, limit: int = 10):
    """Get agent response history."""
    cfg = GraphConfig()
    tracker = ResponseTracker(cfg)
    try:
        # Verify agent exists
        repo = AgentRepository(cfg)
        try:
            agent = await repo.get_agent(agent_id)
            if agent is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Agent {agent_id} not found",
                )
        finally:
            await repo.close()

        history = await tracker.get_response_history(agent_id, limit=limit)
        return AgentHistoryResponse(history=[_turn_to_dict(t) for t in history])
    finally:
        await tracker.close()
