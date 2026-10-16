from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.auth.cookies import verify_csrf
from src.auth.deps import current_user
from src.db.models import User
from src.graph.config_graph import GraphConfig
from src.logging.setup_logging import setup_logging
from src.persona.agent import Agent
from src.persona.repository import PersonaRepository

# Mounted twice by `api_server`: prefix "/api" keeps today's /api/personas/hatch
# alias; "/api/v1" is the canonical surface (R15).
router = APIRouter(
    prefix="/personas", tags=["personas"], dependencies=[Depends(verify_csrf)]
)
logger = setup_logging()


class HatchRequest(BaseModel):
    query: str
    limit: Optional[int] = 10


@router.post("/hatch", response_model=List[dict])
async def hatch_personas(req: HatchRequest, user: User = Depends(current_user)):
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
        return [
            a.model_dump() if hasattr(a, "model_dump") else a.dict() for a in agents
        ]
    finally:
        await repo.close()
