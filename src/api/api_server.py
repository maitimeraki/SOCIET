import asyncio
import uuid
import json
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Optional, AsyncGenerator, Any
from contextlib import asynccontextmanager
from src.api.config_api import (
    UserQuery,
    SimulationAccepted,
    SimulationResponse,
    SimulationRunStatus,
)
from src.graph.config_graph import GraphConfig
from src.graph.models_graph import GraphInputDocument
from src.graph.ontology import OntologyDiscoveryStage
from src.graph.graph_build import GraphExtractionStage
from src.graph.normalization import GraphNormalizationStage
from src.simulation.simulation_engine import SimulationSociety
from src.simulation.world_state import SharedWorldState, MessageBus
from src.simulation.config_world import WorldEvent
from src.llm.client import LLMClient, global_llm_client
from src.llm.config_llm import get_llm_config


@asynccontextmanager
async def lifespan(app: FastAPI)-> AsyncGenerator[None, None]:
    """Startup and shutdown events for the API server"""
    # 1. Setup: Everything before 'yield' runs on STARTUP
    print("Starting up API server...")
    client = global_llm_client  # Use the global client instance
    # Test LLM connectivity, warm up caches, etc.
    try:
        test = await client.generate(
            "You are a test system.", 
            "Say 'OK' if working.",
            provider=get_llm_config().default_llm_provider,
            model=get_llm_config().default_model,
            temperature=0.7
        )
        if test:
            print(f"✅ LLM connected: {get_llm_config().default_llm_provider}")
        
    except Exception as e:
        print(f"LLM connectivity test failed: {e}")
        raise RuntimeError("LLM provider is not reachable. Check configuration.")

    yield # The app runs while it's paused here
    # 2. Shutdown: Everything after 'yield' runs on SHUTDOWN

app = FastAPI(
    title="Socirty Simulator API",
    description="API for simulating societal debates using AI agents",
    version="1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


AVAILABLE_DOMAINS = [
    "finance",
    "risk_management",
    "business_development",
    "market_analysis",
    "anthropology",
    "international_business",
    "cultural_studies",
    "international_law",
    "gdpr",
    "trade_regulation",
    "emerging_tech",
    "ai",
    "innovation",
    "logic",
    "philosophy",
    "systems_thinking",
]

SIMULATION_RUNS: Dict[str, SimulationRunStatus] = {}
_RUNS_LOCK = asyncio.Lock()


def _strip_json_fences(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()
    return cleaned


async def _run_simulation_pipeline(query: UserQuery) -> SimulationResponse:
    """Shared simulation logic used by sync and async endpoints."""
    llm_cfg = get_llm_config()

    world_params = await parse_scenario(
        scenario=query.scenario,
        context=query.context or {},
        provider=llm_cfg.default_llm_provider,
        model=llm_cfg.default_model,
    )

    requested_domains = query.selected_domains or query.required_perspectives or []
    society_config = design_society(
        topic=query.scenario,
        required_perspectives=requested_domains,
        depth=query.simulation_depth,
    )

    inferred_domains = world_params.get("domains", [])
    if inferred_domains:
        society_config["domains"] = sorted(set(society_config["domains"] + inferred_domains))

    world = SharedWorldState()
    bus = MessageBus()
    society = SimulationSociety(world, bus)

    world.inject_event(
        WorldEvent(
            event_type="user_query",
            description=query.scenario,
            severity=0,
            affected_domains=society_config["domains"],
            timestamp=str(datetime.now()),
        )
    )
    world.economic_indicators["user_context"] = query.context or {}

    # Use the async generate method directly as backend for Agent async methods.
    society.recruit_agents(society_config["agents"], global_llm_client.generate)
    result = await society.run_simulation(query.scenario)

    return SimulationResponse(
        society_opinion=result["society_opinion"],
        dissenting_views=result["dissent"]["alternative_views"],
        confidence_metrics={
            "overall_confidence": result["society_opinion"]["confidence"],
            "debate_rounds": result["meta"]["rounds_to_convergence"],
            "debate_intensity": result["meta"]["debate_intensity"],
            "provider": llm_cfg.default_llm_provider,
            "model": llm_cfg.default_model,
            "agent_count": len(society.agents),
        },
        agent_profiles=[
            {
                "name": a.name,
                "expertise": a.domain_expertise,
                "personality": [p.value for p in a.personality],
                "final_stance": "unknown",
            }
            for a in society.agents
        ],
        raw_debate_log=result.get("debate_log") if query.simulation_depth == "deep" else None,
    )


async def _execute_async_run(run_id: str, query: UserQuery) -> None:
    """Background execution for async simulation requests."""
    async with _RUNS_LOCK:
        SIMULATION_RUNS[run_id].status = "running"
        SIMULATION_RUNS[run_id].stage = "simulation_running"
        SIMULATION_RUNS[run_id].progress = 0.2

    try:
        result = await _run_simulation_pipeline(query)
        async with _RUNS_LOCK:
            SIMULATION_RUNS[run_id].status = "completed"
            SIMULATION_RUNS[run_id].stage = "completed"
            SIMULATION_RUNS[run_id].progress = 1.0
            SIMULATION_RUNS[run_id].result = result
    except Exception as exc:
        async with _RUNS_LOCK:
            SIMULATION_RUNS[run_id].status = "failed"
            SIMULATION_RUNS[run_id].stage = "failed"
            SIMULATION_RUNS[run_id].error = str(exc)


@app.post('/simulate/ontology', response_model=Dict[str, List[str]])
async def discover_ontology(documents: List[GraphInputDocument]):
    """Endpoint to discover ontology from documents."""
    discovery_stage = OntologyDiscoveryStage()  
    ontology = await discovery_stage.run(documents=documents)
    return {
        "entity_types": ontology.entity_types,
        "relation_types": ontology.relation_types,
    }
    
    
    
@app.post('/simulate/build_graph', response_model=Dict[str, Any])
async def build_graph(dataset_id: str, documents: List[GraphInputDocument]):
    """Endpoint to build graph from documents using discovered ontology."""
    discovery_stage = OntologyDiscoveryStage()
    ontology = await discovery_stage.run(documents=documents)

    extraction_stage = GraphExtractionStage(GraphConfig())
    chunk_count = await extraction_stage.run(dataset_id=dataset_id, documents=documents, ontology=ontology)

    normalization_stage = GraphNormalizationStage(GraphConfig())
    await normalization_stage.run(dataset_id=dataset_id)

    return {
        "dataset_id": dataset_id,
        "docs": len(documents),
        "chunks": chunk_count,
        "discovered_entity_types": ontology.entity_types,
        "discovered_relation_types": ontology.relation_types,
    }

@app.post("/simulate", response_model=SimulationResponse)
async def create_simulation(query: UserQuery, background_tasks: BackgroundTasks):
    """
    Main endpoint: User input -> Society opinion
    """
    return await _run_simulation_pipeline(query)


@app.post("/simulate/async", response_model=SimulationAccepted)
async def create_simulation_async(query: UserQuery):
    """Queue a simulation and return immediately with run id."""
    run_id = str(uuid.uuid4())
    run_status = SimulationRunStatus(
        run_id=run_id,
        status="queued",
        progress=0.0,
        stage="queued",
    )
    async with _RUNS_LOCK:
        SIMULATION_RUNS[run_id] = run_status

    asyncio.create_task(_execute_async_run(run_id, query))
    return SimulationAccepted(
        run_id=run_id,
        status="queued",
        message="Simulation accepted and queued.",
    )


@app.get("/simulate/{run_id}", response_model=SimulationRunStatus)
async def get_simulation_run(run_id: str):
    """Poll status for asynchronous simulation runs."""
    async with _RUNS_LOCK:
        run = SIMULATION_RUNS.get(run_id)
        if not run:
            return SimulationRunStatus(
                run_id=run_id,
                status="failed",
                progress=0.0,
                stage="not_found",
                error="Run id not found",
            )
        return run
    
async def parse_scenario(
    scenario: str,
    context: Dict,
    provider: Optional[str] = None,
    model: Optional[str] = None
) -> Dict:
    
    world_state_json = json.dumps(context, ensure_ascii=False)
    prompt = f"""
Analyze this business scenario and extract JSON with keys:
- domains: string[]
- time_horizon: string
- risk_factors: string[]
- success_criteria: string[]

Scenario: {scenario}
Context: {world_state_json}
"""
    raw = await global_llm_client.generate(
        system_prompt="You extract structured simulation parameters. Return valid JSON only.",
        user_prompt=prompt,
        provider=provider,
        model=model,
        temperature=0.2
    )

    try:
        parsed = json.loads(_strip_json_fences(raw))
        return {
            "domains": parsed.get("domains", []),
            "time_horizon": parsed.get("time_horizon", "unknown"),
            "risk_factors": parsed.get("risk_factors", []),
            "success_criteria": parsed.get("success_criteria", []),
        }
    except Exception:
        return {
            "domains": [],
            "time_horizon": "unknown",
            "risk_factors": [],
            "success_criteria": []
        }
    
    

def design_society(topic: str, required_perspectives: Optional[List[str]], depth: str) -> Dict:
    base_agents = [
        {
            "name": "Conservative Analyst",
            "domain_expertise": ["finance", "risk_management"],
            "personality": ["pessimist", "conservative", "skeptic"],
            "initial_beliefs": [{"statement": "Market expansion is inherently risky", "confidence": 0.8, "evidence": ["historical volatility"]}]
        },
        {
            "name": "Growth Strategist",
            "domain_expertise": ["business_development", "market_analysis"],
            "personality": ["optimist", "innovator"],
            "initial_beliefs": [{"statement": "First-mover advantage outweighs risks", "confidence": 0.75, "evidence": ["competitive dynamics"]}]
        },
        {
            "name": "Cultural Translator",
            "domain_expertise": ["anthropology", "international_business", "cultural_studies"],
            "personality": ["skeptic", "optimist"],
            "initial_beliefs": [{"statement": "Local adaptation determines success", "confidence": 0.9, "evidence": ["cross-market variance"]}]
        }
    ]

    if "europe" in topic.lower() or "eu" in topic.lower():
        base_agents.append({
            "name": "Regulatory Expert",
            "domain_expertise": ["international_law", "gdpr", "trade_regulation"],
            "personality": ["skeptic", "conservative"],
            "initial_beliefs": [{"statement": "Compliance costs are underestimated", "confidence": 0.85, "evidence": ["regulatory overhead"]}]
        })

    if "tech" in topic.lower() or "ai" in topic.lower():
        base_agents.append({
            "name": "Technology Scout",
            "domain_expertise": ["emerging_tech", "ai", "innovation"],
            "personality": ["innovator", "optimist"],
            "initial_beliefs": [{"statement": "Technology obsoletes old business models", "confidence": 0.8, "evidence": ["adoption curves"]}]
        })

    if depth == "deep":
        base_agents.append({
            "name": "Contrarian",
            "domain_expertise": ["logic", "philosophy", "systems_thinking"],
            "personality": ["skeptic", "pessimist"],
            "initial_beliefs": [{"statement": "Group consensus is often wrong", "confidence": 0.9, "evidence": ["groupthink patterns"]}]
        })

    # Optional perspective filter
    if required_perspectives:
        rp = set(p.lower() for p in required_perspectives)
        base_agents = [
            a for a in base_agents
            if any(d.lower() in rp for d in a["domain_expertise"]) or a["name"] in {"Conservative Analyst", "Growth Strategist"}
        ]

    return {
        "agents": base_agents,
        "domains": sorted(set(d for a in base_agents for d in a["domain_expertise"]))
    }




if __name__=="__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)