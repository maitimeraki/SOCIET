import asyncio
import uuid
import json
import sys
import logging
from pathlib import Path
from src.logging.setup_logging import setup_logging 
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Optional, AsyncGenerator, Any, Set
from contextlib import asynccontextmanager
from src.api.config_api import (
    UserQuery,
    SimulationAccepted,
    SimulationResponse,
    SimulationRunStatus,
    OntologyAccepted,
    OntologyRunStatus,
    OntologyResult,
    JobMode,
    ChunkProgress,
    UnifiedJobResult
)
from src.graph.config_graph import GraphConfig
from src.graph.models_graph import GraphInputDocument
from src.graph.ontology import OntologyDiscoveryStage
from src.graph.graph_build import GraphExtractionStage
from src.graph.normalization import GraphNormalizationStage
from src.simulation.simulation_engine import SimulationSociety
from src.simulation.world_state import SharedWorldState, MessageBus
from src.simulation.config_world import WorldEvent
from src.llm.client import global_llm_client
from src.llm.config_llm import get_llm_config


# Configure basic logging
logging.basicConfig(
    level=logging.INFO,  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)  # Output to terminal
    ]
)
logging.basicConfig(level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s")

# # Create logger instance
# logger = logging.getLogger(__name__)
logger = setup_logging()  # Ensure logging is configured with handler clearing to prevent duplication

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


RUNS: Dict[str, Dict[str, Any]] = {}
_RUNS_LOCK = asyncio.Lock()
_RUNS_RUNTIME_DIR = Path("src/api/runtime/jobs")
_RUNS_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

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


async def _persist_run(job_id: str, run: Dict[str, Any]) -> None:
    path = _RUNS_RUNTIME_DIR / f"{job_id}.json"
    await asyncio.to_thread(path.write_text, json.dumps(run, ensure_ascii=False, indent=2), "utf-8")

def _chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    step = max(1, chunk_size - overlap)
    chunks: List[str] = []
    for start in range(0, len(cleaned), step):
        chunk = cleaned[start:start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
    return chunks

def _chunk_documents(
    documents: List[GraphInputDocument],
    chunk_size: int,
    overlap: int,
) -> List[GraphInputDocument]:
    chunks: List[GraphInputDocument] = []
    for doc in documents:
        doc_chunks = _chunk_text(doc.text, chunk_size, overlap)
        for idx, chunk in enumerate(doc_chunks):
            chunks.append(
                GraphInputDocument(
                    document_id=f"{doc.document_id}_chunk_{idx}",
                    title=doc.title,
                    text=chunk,
                    metadata={"source_document_id": doc.document_id, **(doc.metadata or {})},
                )
            )
    return chunks
def _merge_labels(items: List[str], fallback: str) -> List[str]:
    seen: Set[str] = set()
    merged: List[str] = []
    for item in items:
        label = (item or "").strip().upper().replace(" ", "_")
        if label and label not in seen:
            seen.add(label)
            merged.append(label)
    if merged is None or len(merged) == 0:
        merged = [fallback]
    return merged

async def _process_chunk(
    mode: JobMode,
    dataset_id: str,
    chunk_doc: GraphInputDocument,
    discovery_stage: OntologyDiscoveryStage,
    extraction_stage: Optional[GraphExtractionStage],
    timeout_seconds: int,
    retry_attempts: int,
    retry_backoff_seconds: float,
) -> ChunkProgress:
    last_exc: Optional[Exception] = None
    ontology = None
    logger.info(f"Start of chunk progress for {chunk_doc.document_id} ")
    for attempt in range(max(1, retry_attempts)):
        try:
            ontology = await asyncio.wait_for(
                discovery_stage.run(documents=[chunk_doc], sample_size=1),
                timeout=timeout_seconds,
            )
            break
        except Exception as exc:
            last_exc = exc
            if attempt < retry_attempts - 1:
                await asyncio.sleep(retry_backoff_seconds * (2 ** attempt))
                
            logger.warning(f"Ontology discovery attempt {attempt + 1} failed for {chunk_doc.document_id}: {exc}. Retrying...")

    if ontology is None:
        raise RuntimeError(f"ontology discovery failed for {chunk_doc.document_id}: {last_exc}")

    docs_built = 0
    if mode == "build_graph":
        if extraction_stage is None:
            raise RuntimeError("extraction_stage is required for build_graph mode")
        
        logger.info(f"Start building the graph of {chunk_doc.document_id}")
        try:
            docs_built = await extraction_stage.run(
                dataset_id=dataset_id,
                documents=[chunk_doc],
                ontology=ontology
            )
            logger.info(f"Complete building graph of {chunk_doc.document_id}")
        except asyncio.TimeoutError:
            logger.error(f"Graph extraction timeout for {chunk_doc.document_id}")
            raise
        except Exception as exc:
            logger.error(f"Graph extraction failed for {chunk_doc.document_id}: {exc}")
            raise  # Re-raise to properly signal failure

    view = ontology.to_public_view()
    return {
        "entity_types": view.entity_types, # return types -> List[str]
        "relation_types": view.relation_types, # return types -> List[str]
        "docs_built": docs_built, 
    }

async def _execute_unified_job(
    job_id: str,
    mode: JobMode,
    dataset_id: str,
    documents: List[GraphInputDocument],
) -> None:
    cfg = GraphConfig()
    discovery_stage = OntologyDiscoveryStage(model=cfg.discovery_model, temperature=cfg.temperature)
    extraction_stage = GraphExtractionStage(cfg) if mode == "build_graph" else None
    normalization_stage = GraphNormalizationStage(cfg) if mode == "build_graph" else None

    chunks = _chunk_documents(documents, cfg.ontology_chunk_size_chars, cfg.ontology_chunk_overlap_chars) # return types -> List[GraphInputDocument]
    total_chunks = len(chunks)

    async with _RUNS_LOCK:
        RUNS[job_id]["status"] = "running"
        RUNS[job_id]["stage"] = f"{mode}_running"
        RUNS[job_id]["progress"] = 0.05
        RUNS[job_id]["result"] = {
            "dataset_id": dataset_id,
            "chunks_total": total_chunks,
            "chunks_completed": 0,
            "docs_built": 0,
            "entity_types": [],
            "relation_types": [],
        }
        await _persist_run(job_id, RUNS[job_id])

    if total_chunks == 0:
        async with _RUNS_LOCK:
            RUNS[job_id]["status"] = "completed"
            RUNS[job_id]["stage"] = "completed"
            RUNS[job_id]["progress"] = 1.0
            RUNS[job_id]["result"] = {
                "dataset_id": dataset_id,
                "chunks_total": 0,
                "chunks_completed": 0,
                "docs_built": 0,
                "entity_types": ["ENTITY"],
                "relation_types": ["RELATED_TO"],
            }
            await _persist_run(job_id, RUNS[job_id])
        return

    semaphore = asyncio.Semaphore(max(1, cfg.ontology_max_concurrency))
    entity_accumulator: List[str] = []
    relation_accumulator: List[str] = []
    docs_built = 0
    completed = 0

    async def _worker(chunk_doc: GraphInputDocument) -> ChunkProgress:
        async with semaphore:
             # ✅ FIX 6: Add small delay between chunks
            await asyncio.sleep(0.1)
            return await _process_chunk(
                mode=mode,
                dataset_id=dataset_id,
                chunk_doc=chunk_doc,
                discovery_stage=discovery_stage,
                extraction_stage=extraction_stage,
                timeout_seconds=cfg.discovery_timeout_seconds,
                retry_attempts=cfg.discovery_retry_attempts,
                retry_backoff_seconds=cfg.discovery_retry_backoff_seconds,
            )

    try:
        tasks = [asyncio.create_task(_worker(chunk)) for chunk in chunks]
        for fut in asyncio.as_completed(tasks):
            partial = await fut
            completed += 1
            docs_built += int(partial.get("docs_built", 0))
            entity_accumulator.extend(partial.get("entity_types", []))
            relation_accumulator.extend(partial.get("relation_types", []))

            async with _RUNS_LOCK:
                RUNS[job_id]["stage"] = f"{mode}_running"
                RUNS[job_id]["progress"] = min(0.95, completed / max(1, total_chunks))
                RUNS[job_id]["result"] = {
                    "dataset_id": dataset_id,
                    "chunks_total": total_chunks,
                    "chunks_completed": completed,
                    "docs_built": docs_built,
                    "entity_types": _merge_labels(entity_accumulator, "ENTITY"),
                    "relation_types": _merge_labels(relation_accumulator, "RELATED_TO"),
                }
                await _persist_run(job_id, RUNS[job_id])

        if mode == "build_graph" and normalization_stage is not None:
            await normalization_stage.run(dataset_id=dataset_id)

        async with _RUNS_LOCK:
            RUNS[job_id]["status"] = "completed"
            RUNS[job_id]["stage"] = "completed"
            RUNS[job_id]["progress"] = 1.0
            await _persist_run(job_id, RUNS[job_id])

    except Exception as exc:
        async with _RUNS_LOCK:
            RUNS[job_id]["status"] = "failed"
            RUNS[job_id]["stage"] = "failed"
            RUNS[job_id]["error"] = str(exc)
            await _persist_run(job_id, RUNS[job_id])
            
               
@app.post("/simulate/ontology", status_code=status.HTTP_202_ACCEPTED)
async def discover_ontology_async(dataset_id: str, documents: List[GraphInputDocument]):
    job_id = str(uuid.uuid4())
    run = {
        "job_id": job_id,
        "mode": "ontology",
        "status": "queued",
        "progress": 0.0,
        "stage": "queued",
        "error": None,
        "result": None,
    }
    async with _RUNS_LOCK:
        RUNS[job_id] = run
        await _persist_run(job_id, run)

    asyncio.create_task(_execute_unified_job(job_id, "ontology", dataset_id, documents))
    return {"job_id": job_id, "status": "queued", "message": "Ontology job accepted."}


@app.post("/simulate/build_graph", status_code=status.HTTP_202_ACCEPTED)
async def build_graph_async(dataset_id: str, documents: List[GraphInputDocument]):
    job_id = str(uuid.uuid4())
    run = {
        "job_id": job_id,
        "mode": "build_graph",
        "status": "queued",
        "progress": 0.0,
        "stage": "queued",
        "error": None,
        "result": None,
    }
    async with _RUNS_LOCK:
        RUNS[job_id] = run
        await _persist_run(job_id, run)

    asyncio.create_task(_execute_unified_job(job_id, "build_graph", dataset_id, documents))
    return {"job_id": job_id, "status": "queued", "message": "Build graph job accepted."}

@app.get("/simulate/jobs/{job_id}")
async def get_job(job_id: str):
    async with _RUNS_LOCK:
        run = RUNS.get(job_id)
        if run:
            return run

    path = _RUNS_RUNTIME_DIR / f"{job_id}.json"
    if path.exists():
        payload = await asyncio.to_thread(path.read_text, "utf-8")
        return json.loads(payload)

    return {"job_id": job_id, "status": "failed", "stage": "not_found", "error": "job id not found"}  
    
@app.post("/simulate", response_model=SimulationResponse)
async def create_simulation(query: UserQuery, background_tasks: BackgroundTasks):
    """
    Main endpoint: User input -> Society opinion
    """
    return await _run_simulation_pipeline(query)


# @app.post("/simulate/async", response_model=SimulationAccepted)
# async def create_simulation_async(query: UserQuery):
#     """Queue a simulation and return immediately with run id."""
#     run_id = str(uuid.uuid4())
#     run_status = SimulationRunStatus(
#         run_id=run_id,
#         status="queued",
#         progress=0.0,
#         stage="queued",
#     )
#     async with _RUNS_LOCK:
#         SIMULATION_RUNS[run_id] = run_status

#     asyncio.create_task(_execute_async_run(run_id, query))
#     return SimulationAccepted(
#         run_id=run_id,
#         status="queued",
#         message="Simulation accepted and queued.",
#     )


# @app.get("/simulate/{run_id}", response_model=SimulationRunStatus)
# async def get_simulation_run(run_id: str):
#     """Poll status for asynchronous simulation runs."""
#     async with _RUNS_LOCK:
#         run = SIMULATION_RUNS.get(run_id)
#         if not run:
#             return SimulationRunStatus(
#                 run_id=run_id,
#                 status="failed",
#                 progress=0.0,
#                 stage="not_found",
#                 error="Run id not found",
#             )
#         return run
    
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