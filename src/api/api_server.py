import asyncio
import uuid
import json
import sys
import logging
from pathlib import Path
from src.logging.setup_logging import setup_logging
from src.api.middleware import LoggingMiddleware
from fastapi import FastAPI, BackgroundTasks, HTTPException, status, Request
from fastapi.responses import JSONResponse
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
    UnifiedJobResult,
)
from src.graph.config_graph import GraphConfig
from src.graph.models_graph import GlobalInputDocument, ProcessedChunk
from src.graph.ontology import OntologyDiscoveryStage
from src.graph.graph_build import GraphExtractionStage
from src.graph.normalization import GraphNormalizationStage
from src.llm.client import global_llm_client
from src.llm.config_llm import get_llm_config
from src.utils.chunkProcessor import ChunkProcessor, split_text_sentences

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
    """Startup and shutdown events for the API server.

    On startup:
      1. Apply Neo4j schema bootstrap (constraints, indexes, vector index)
         so writes and vector retrieval don't fail at runtime.
      2. Probe the LLM provider.
    """
    # 1. Setup: Everything before 'yield' runs on STARTUP
    logger.info("Starting up API server...")

    # 1a. Apply Neo4j schema bootstrap (idempotent).
    try:
        from neo4j import AsyncGraphDatabase
        from src.graph.config_graph import GraphConfig
        from src.graph.neo4j_bootstrap import ensure_schema

        cfg = GraphConfig()
        driver = AsyncGraphDatabase.driver(
            cfg.neo4j_uri,
            auth=(cfg.neo4j_username, cfg.neo4j_password),
        )
        try:
            result = await ensure_schema(driver, cfg.neo4j_database)
            logger.info(
                "Neo4j schema bootstrap: applied=%d failed=%d",
                len(result["applied"]),
                len(result["failed"]),
            )
        finally:
            await driver.close()
    except Exception:
        # Don't block startup if Neo4j is unreachable -- log and let
        # individual requests surface the failure.
        logger.exception("Neo4j schema bootstrap failed; continuing startup")

    # 1b. LLM connectivity probe.
    client = global_llm_client
    try:
        test = await client.generate(
            "You are a test system.",
            "Say 'OK' if working.",
            provider=get_llm_config().default_llm_provider,
            model=get_llm_config().default_model,
            temperature=0.7,
        )
        if test:
            logger.info(f"LLM connected: {get_llm_config().default_llm_provider}")
    except Exception as e:
        logger.exception(f"LLM connectivity test failed: {e}")
        raise RuntimeError("LLM provider is not reachable. Check configuration.")

    yield
    # 2. Shutdown: Everything after 'yield' runs on SHUTDOWN

app = FastAPI(
    title="Socirty Simulator API",
    description="API for simulating societal debates using AI agents",
    version="1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler with correlation ID support."""
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    logger.error(f"Unhandled exception [{correlation_id}]: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal server error", "correlation_id": correlation_id},
    )


# Persona API (hatch personas from user query)
from src.api.persona_api import router as persona_router
app.include_router(persona_router)
# Debate API
from src.api.debate_api import router as debate_router
app.include_router(debate_router)


RUNS: Dict[str, Dict[str, Any]] = {}
_RUNS_LOCK = asyncio.Lock()
_RUNS_RUNTIME_DIR = Path("src/api/runtime/jobs")
_RUNS_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

async def _persist_run(job_id: str, run: Dict[str, Any]) -> None:
    path = _RUNS_RUNTIME_DIR / f"{job_id}.json"
    await asyncio.to_thread(path.write_text, json.dumps(run, ensure_ascii=False, indent=2), "utf-8")

async def _chunk_documents(
    documents: List[GlobalInputDocument],
    chunk_size: int,
    overlap: int,
) -> List[ProcessedChunk]:
    processor = ChunkProcessor()

    chunks: List[ProcessedChunk] = []
    for doc in documents:
        # Sentence-aware splitting (single owner: chunkProcessor.split_text_sentences)
        doc_chunks = split_text_sentences(doc.text or "", chunk_size, overlap)

        for idx, chunk_text in enumerate(doc_chunks):
            processed_chunk = await processor.process_document(
                chunk=chunk_text,
                chunk_index=idx,
                parent_doc_id=doc.document_id,
                metadata=doc.metadata or {},
            )
            chunks.append(processed_chunk)

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
    chunk_doc: ProcessedChunk,
    discovery_stage: OntologyDiscoveryStage,
    extraction_stage: Optional[GraphExtractionStage],
    timeout_seconds: int,
    retry_attempts: int,
    retry_backoff_seconds: float,
) -> ChunkProgress:
    last_exc: Optional[Exception] = None
    ontology = None
    logger.info(f"Start of chunk progress for {chunk_doc.chunk_id} ")
    for attempt in range(max(1, retry_attempts)):
        try:
            ontology = await asyncio.wait_for(
                discovery_stage.run(documents=[chunk_doc], sample_size=1),
                timeout=timeout_seconds,
            )
            break
        except asyncio.TimeoutError:
            logger.warning(f"Ontology discovery timeout for {chunk_doc.chunk_id} on attempt {attempt + 1}")
            last_exc = RuntimeError(f"Ontology discovery timed out after {timeout_seconds} seconds")
        except Exception as exc:
            last_exc = exc
            if attempt < retry_attempts - 1:
                await asyncio.sleep(retry_backoff_seconds * (2 ** attempt))
                
            logger.warning(f"Ontology discovery attempt {attempt + 1} failed for {chunk_doc.chunk_id}: {exc}. Retrying...")

    if ontology is None:
        raise RuntimeError(f"ontology discovery failed for {chunk_doc.chunk_id}: {last_exc}")

    docs_built = 0
    if mode == "build_graph":
        if extraction_stage is None:
            raise RuntimeError("extraction_stage is required for build_graph mode")
        
        logger.info(f"Start building the graph of {chunk_doc.chunk_id}")
        try:
            docs_built = await extraction_stage.run(
                dataset_id=dataset_id,
                documents=[chunk_doc],
                ontology=ontology
            )
            logger.info(f"Complete building graph of {chunk_doc.chunk_id}")
        except asyncio.TimeoutError:
            logger.error(f"Graph extraction timeout for {chunk_doc.chunk_id}")
            raise
        except Exception as exc:
            logger.error(f"Graph extraction failed for {chunk_doc.chunk_id}: {exc}")
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
    documents: List[GlobalInputDocument],
) -> None:
    cfg = GraphConfig()
    discovery_stage = OntologyDiscoveryStage(model=cfg.discovery_model, temperature=cfg.temperature)
    extraction_stage = GraphExtractionStage(cfg) if mode == "build_graph" else None
    normalization_stage = GraphNormalizationStage(cfg) if mode == "build_graph" else None

    chunks = await _chunk_documents(documents, cfg.ontology_chunk_size_chars, cfg.ontology_chunk_overlap_chars)
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

    async def _worker(chunk_doc: ProcessedChunk) -> ChunkProgress:
        async with semaphore:
             # ✅ FIX 6: Add small delay between chunks
            await asyncio.sleep(0.1)
            return await _process_chunk(
                mode=mode,
                # dataset_id should be passed from frontend when users put their documents, not generated here
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
        logger.info(f"Started {len(tasks)} tasks for job {job_id} in mode {mode}")
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
            # normalization_stage is our embedded class instance
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
async def discover_ontology_async(dataset_id: str, documents: List[GlobalInputDocument]):
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
async def build_graph_async(dataset_id: str, documents: List[GlobalInputDocument]):
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


@app.post("/simulate/async", status_code=status.HTTP_202_ACCEPTED)
async def create_simulation_async(query: UserQuery):
    raise HTTPException(
        status_code=501,
        detail="Legacy /simulate/async retired — use POST /simulate/debate (graph-backed).",
    )


@app.post("/simulate", response_model=SimulationResponse)
async def create_simulation(query: UserQuery, background_tasks: BackgroundTasks):
    raise HTTPException(
        status_code=501,
        detail="Legacy /simulate retired — use POST /simulate/debate (graph-backed).",
    )


@app.post('/simulate/normalize_graph', status_code=status.HTTP_202_ACCEPTED)
async def normalize_graph(dataset_id: str, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    run = {
        "job_id": job_id,
        "mode": "normalize_graph",
        "status": "queued",
        "progress": 0.0,
        "stage": "queued",
        "error": None,
        "result": None,
    }
    async with _RUNS_LOCK:
        RUNS[job_id] = run
        await _persist_run(job_id, run)

    async def _normalize():
        try:
            cfg = GraphConfig()
            normalization_stage = GraphNormalizationStage(cfg)
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

    asyncio.create_task(_normalize())
    return {"job_id": job_id, "status": "queued", "message": "Graph normalization job accepted."}


if __name__=="__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "version": "1.0",
        "active_jobs": len(RUNS),
    }