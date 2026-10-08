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
from typing import TYPE_CHECKING, List, Dict, Optional, AsyncGenerator, Any, Set
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
from src.graph.models_graph import GlobalInputDocument, ProcessedChunk, LocalOntology
from src.graph.ontology import OntologyDiscoveryStage
from src.graph.vocabulary import discover_vocabulary
from src.graph.normalization import GraphNormalizationStage
from src.llm.client import global_llm_client
from src.llm.config_llm import get_llm_config
from src.utils.chunkProcessor import ChunkProcessor, split_text_sentences

if TYPE_CHECKING:
    # Annotation-only: `_process_document`'s `extraction_stage` hint. The runtime
    # import stays lazy inside `_execute_unified_job` (see the comment there).
    from src.graph.graph_build import GraphExtractionStage

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
            model=get_llm_config().debate_model,
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
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173","*"],
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

# Ingest API (documents → GlobalInputDocument payloads)
from src.api.ingest_api import router as ingest_router
app.include_router(ingest_router)

# Graph streaming API (live build progress over WebSocket)
from src.api.graph_stream_api import router as graph_stream_router
app.include_router(graph_stream_router)


RUNS: Dict[str, Dict[str, Any]] = {}
_RUNS_LOCK = asyncio.Lock()
_RUNS_RUNTIME_DIR = Path("src/api/runtime/jobs")
_RUNS_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

async def _persist_run(job_id: str, run: Dict[str, Any]) -> None:
    path = _RUNS_RUNTIME_DIR / f"{job_id}.json"
    await asyncio.to_thread(path.write_text, json.dumps(run, ensure_ascii=False, indent=2), "utf-8")


async def _ontology_from_run(ontology_job_id: Optional[str]) -> Optional[LocalOntology]:
    """The completed ontology job's merged schema, or None if absent/not finished.

    Never raises: `_persist_run` writes non-atomically, so a crash mid-write
    leaves invalid JSON — a raising read here would strand the build job in
    "queued" forever. A bad read degrades to the per-chunk discovery path.
    """
    if not ontology_job_id:
        return None
    try:
        run = RUNS.get(ontology_job_id)
        if run is None:
            path = _RUNS_RUNTIME_DIR / f"{ontology_job_id}.json"
            if path.exists():
                run = json.loads(await asyncio.to_thread(path.read_text, "utf-8"))
        payload = ((run or {}).get("result") or {}).get("ontology")
        return LocalOntology.model_validate(payload) if payload else None
    except Exception as exc:
        logger.warning(
            f"Could not load ontology from job {ontology_job_id} ({exc}) — falling back to per-chunk discovery"
        )
        return None


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

async def _discover_for_chunk(
    discovery_stage: OntologyDiscoveryStage,
    chunk_doc: ProcessedChunk,
    timeout_seconds: int,
    retry_attempts: int,
    retry_backoff_seconds: float,
) -> LocalOntology:
    """One bounded discovery call for this chunk, retried on failure."""
    last_exc: Optional[Exception] = None
    for attempt in range(max(1, retry_attempts)):
        try:
            return await asyncio.wait_for(
                discovery_stage.run(documents=[chunk_doc], sample_size=1),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Ontology discovery timeout for {chunk_doc.chunk_id} on attempt {attempt + 1}")
            last_exc = RuntimeError(f"Ontology discovery timed out after {timeout_seconds} seconds")
        except Exception as exc:
            last_exc = exc
            if attempt < retry_attempts - 1:
                await asyncio.sleep(retry_backoff_seconds * (2 ** attempt))
            logger.warning(f"Ontology discovery attempt {attempt + 1} failed for {chunk_doc.chunk_id}: {exc}. Retrying...")
    raise RuntimeError(f"ontology discovery failed for {chunk_doc.chunk_id}: {last_exc}")


async def _discover_dataset_vocabulary(
    chunks: List[ProcessedChunk],
    discovery_stage: OntologyDiscoveryStage,
    timeout_seconds: int,
    retry_attempts: int,
    retry_backoff_seconds: float,
    sample_size: int,
    max_labels: int,
) -> LocalOntology:
    """One bounded dataset-wide vocabulary call, retried on failure.

    Same bound/backoff shape as `_discover_for_chunk`: a hung or transiently
    failing call must fail inside the caller's window rather than escape it."""
    last_exc: Optional[Exception] = None
    for attempt in range(max(1, retry_attempts)):
        try:
            return await asyncio.wait_for(
                discover_vocabulary(
                    chunks,
                    sample_size=sample_size,
                    max_labels=max_labels,
                    stage=discovery_stage,
                ),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Dataset vocabulary discovery timeout on attempt {attempt + 1}")
            last_exc = RuntimeError(f"dataset vocabulary discovery timed out after {timeout_seconds} seconds")
        except Exception as exc:
            last_exc = exc
            if attempt < retry_attempts - 1:
                await asyncio.sleep(retry_backoff_seconds * (2 ** attempt))
            logger.warning(f"Dataset vocabulary discovery attempt {attempt + 1} failed: {exc}. Retrying...")
    raise RuntimeError(f"dataset vocabulary discovery failed: {last_exc}")


async def _process_chunk(
    chunk_doc: ProcessedChunk,
    discovery_stage: OntologyDiscoveryStage,
    timeout_seconds: int,
    retry_attempts: int,
    retry_backoff_seconds: float,
) -> ChunkProgress:
    ontology = await _discover_for_chunk(
        discovery_stage, chunk_doc, timeout_seconds, retry_attempts, retry_backoff_seconds
    )
    view = ontology.to_public_view()
    return {
        "entity_types": view.entity_types,
        "relation_types": view.relation_types,
        "docs_built": 0,
        "ontology": ontology.model_dump(),
    }


async def _process_document(
    dataset_id: str,
    doc_chunks: List[ProcessedChunk],
    ontology: LocalOntology,
    extraction_stage: "GraphExtractionStage",
    job_id: Optional[str] = None,
) -> ChunkProgress:
    """Build-mode worker: ONE graph build per source document, using the
    dataset-wide vocabulary the caller resolved (one call per dataset)."""
    try:
        docs_built = await extraction_stage.run(
            dataset_id=dataset_id,
            documents=doc_chunks,
            ontology=ontology,
            job_id=job_id,
        )
    except asyncio.TimeoutError:
        logger.error(f"Graph extraction timeout for document {doc_chunks[0].parent_doc_id}")
        raise
    except Exception as exc:
        logger.error(f"Graph extraction failed for document {doc_chunks[0].parent_doc_id}: {exc}")
        raise

    view = ontology.to_public_view()
    return {
        "entity_types": view.entity_types,
        "relation_types": view.relation_types,
        "docs_built": docs_built,
        "ontology": None,
    }

async def _execute_unified_job(
    job_id: str,
    mode: JobMode,
    dataset_id: str,
    documents: List[GlobalInputDocument],
    ontology_job_id: Optional[str] = None,
) -> None:
    cfg = GraphConfig()
    # Lazy: graph_build pulls in llama_index graph stores at import time, and
    # tests/graph/test_graph_build.py mocks llama_index at its own import — a
    # module-scope import here would bypass that mock and hit a live Neo4j.
    from src.graph.graph_build import GraphExtractionStage

    provided_ontology = await _ontology_from_run(ontology_job_id) if mode == "build_graph" else None
    if mode == "build_graph" and ontology_job_id and provided_ontology is None:
        logger.warning(f"ontology job {ontology_job_id} has no completed ontology — falling back to a dataset-wide spread-sample vocabulary")

    discovery_stage = (
        OntologyDiscoveryStage(
            model=cfg.discovery_model,
            temperature=cfg.temperature,
            timeout=min(60.0, cfg.discovery_timeout_seconds),
        )
        if provided_ontology is None
        else None
    )
    extraction_stage = GraphExtractionStage(cfg) if mode == "build_graph" else None
    normalization_stage = GraphNormalizationStage(cfg) if mode == "build_graph" else None

    chunks = await _chunk_documents(documents, cfg.chunk_size_tokens, cfg.chunk_overlap_tokens)
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
    chunk_ontologies: List[dict] = []
    docs_built = 0
    completed = 0

    if mode == "ontology":
        units = [(c.parent_doc_id, [c]) for c in chunks]
    else:
        by_doc: Dict[str, List[ProcessedChunk]] = {}
        for c in chunks:
            by_doc.setdefault(c.parent_doc_id, []).append(c)
        units = list(by_doc.items())

    async def _worker(doc_id: str, doc_chunks: List[ProcessedChunk]) -> ChunkProgress:
        async with semaphore:
            if mode == "ontology":
                return await _process_chunk(
                    doc_chunks[0],
                    discovery_stage,
                    cfg.discovery_timeout_seconds,
                    cfg.discovery_retry_attempts,
                    cfg.discovery_retry_backoff_seconds,
                )
            return await _process_document(
                dataset_id=dataset_id,
                doc_chunks=doc_chunks,
                ontology=provided_ontology,
                extraction_stage=extraction_stage,
                job_id=job_id,
            )

    try:
        if mode == "build_graph" and provided_ontology is None:
            # One vocabulary per dataset: a single bounded discovery call over a
            # spread sample, replacing per-chunk discovery + union. Inside the
            # try so a terminal failure persists the job as "failed".
            provided_ontology = await _discover_dataset_vocabulary(
                chunks,
                discovery_stage,
                cfg.discovery_timeout_seconds,
                cfg.discovery_retry_attempts,
                cfg.discovery_retry_backoff_seconds,
                cfg.vocabulary_sample_size,
                cfg.vocabulary_max_labels,
            )

        tasks: List[asyncio.Task] = []
        counts: Dict[asyncio.Task, int] = {}
        for doc_id, doc_chunks in units:
            t = asyncio.create_task(_worker(doc_id, doc_chunks))
            tasks.append(t)
            counts[t] = len(doc_chunks)
        logger.info(f"Started {len(tasks)} tasks for job {job_id} in mode {mode}")

        # `asyncio.as_completed` yields coroutines on Python 3.11 (not the tasks),
        # so the yielded item can't be keyed back to its chunk count. `asyncio.wait`
        # yields the finished tasks themselves, keeping the counts map exact.
        pending: Set[asyncio.Task] = set(tasks)
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for fut in done:
                partial = fut.result()
                completed += counts[fut]
                docs_built += int(partial.get("docs_built", 0))
                entity_accumulator.extend(partial.get("entity_types", []))
                relation_accumulator.extend(partial.get("relation_types", []))
                if partial.get("ontology") is not None:
                    chunk_ontologies.append(partial["ontology"])

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

        # Job-scoped failure verdict (R17): a document whose chunks all failed
        # contributes nothing (graph_build._run_async skips it without raising),
        # so the run is fatal ONLY when the DATASET-WIDE total is zero. A build
        # in which some documents landed is still a success.
        if mode == "build_graph" and total_chunks > 0 and docs_built == 0:
            raise RuntimeError(
                f"all {total_chunks} chunks failed across every document for dataset {dataset_id}"
            )

        if mode == "build_graph" and normalization_stage is not None:
            # normalization_stage is our embedded class instance
            await normalization_stage.run(dataset_id=dataset_id)

        if mode == "ontology" and chunk_ontologies:
            merged = LocalOntology.merge([LocalOntology.model_validate(o) for o in chunk_ontologies])
            RUNS[job_id]["result"]["ontology"] = merged.model_dump()
            RUNS[job_id]["result"]["entity_types"] = merged.entity_labels or ["ENTITY"]
            RUNS[job_id]["result"]["relation_types"] = merged.relation_labels or ["RELATED_TO"]

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
async def build_graph_async(
    dataset_id: str,
    documents: List[GlobalInputDocument],
    ontology_job_id: Optional[str] = None,
):
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

    asyncio.create_task(
        _execute_unified_job(job_id, "build_graph", dataset_id, documents, ontology_job_id=ontology_job_id)
    )
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