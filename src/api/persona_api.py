from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from src.graph.config_graph import GraphConfig
from src.persona.agent import Agent
from src.persona.repository import PersonaRepository
from src.logging.setup_logging import setup_logging


router = APIRouter(prefix="/api/personas", tags=["personas"])
logger = setup_logging()


class HatchRequest(BaseModel):
    query: str
    limit: Optional[int] = 10


@router.post("/hatch", response_model=List[dict])
async def hatch_personas(req: HatchRequest):
    """Hatch agents from a natural-language query.

    Returns the canonical Agent model (bio, stance, confidence, conviction,
    cior, domain_tags, summary_provenance, confidence_breakdown,
    graph_snapshot) for every synthesized agent.
    """
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="query is required")

    cfg = GraphConfig()
    repo = PersonaRepository(
        neo4j_uri=cfg.neo4j_uri,
        neo4j_user=cfg.neo4j_username,
        neo4j_password=cfg.neo4j_password,
        neo4j_database=cfg.neo4j_database,
    )

    try:
        agents: List[Agent] = await repo.create_agent_profiles_from_query(
            user_query=req.query,
            dataset_id=cfg.neo4j_database,
            max_agents=req.limit or 10,
        )
        # Pydantic v2 uses .model_dump(); v1 used .dict(). Support both.
        return [a.model_dump() if hasattr(a, "model_dump") else a.dict() for a in agents]
    finally:
        await repo.close()
