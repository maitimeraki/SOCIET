from fastapi import APIRouter, HTTPException
from src.api.config_api import GraphDebateQuery, GraphDebateResponse
from src.simulation.graph_debate_engine import GraphDebateSimulation
from src.persona.repository import PersonaRepository
from src.persona.fetcher import PersonaFetcher
from src.llm.config_llm import get_llm_config
from src.llm.client import LLMClient
from src.graph.config_graph import GraphConfig
from typing import Dict, Any

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.post("/debate", response_model=GraphDebateResponse)
async def start_graph_debate(query: GraphDebateQuery):
    if not query.topic or not query.topic.strip():
        raise HTTPException(status_code=400, detail="topic is required")

    # create repo + fetcher + llm client using the graph config
    cfg = GraphConfig()
    repo = PersonaRepository(
        neo4j_uri=cfg.neo4j_uri,
        neo4j_user=cfg.neo4j_username,
        neo4j_password=cfg.neo4j_password,
        neo4j_database=cfg.neo4j_database,
    )
    fetcher = PersonaFetcher(repo=repo)

    llm_cfg = get_llm_config()
    llm_client = LLMClient()

    sim = GraphDebateSimulation(
        repo=repo,
        persona_fetcher=fetcher,
        llm_client=llm_client,
        archetype_label=query.archetype_label,
        provider=llm_cfg.default_llm_provider,
        model=llm_cfg.default_model,
    )

    try:
        # load agents (honors provided agent_names or picks from graph)
        await sim.load_agents(max_agents=query.max_agents, include_names=query.agent_names or None)
        result = await sim.run(topic=query.topic, rounds=query.rounds, max_agents=query.max_agents, dataset_id=query.dataset_id)
        # GraphDebateSimulation.run returns a dict matching GraphDebateResponse
        return GraphDebateResponse(**result)
    finally:
        try:
            await sim.close()
        except Exception:
            pass
