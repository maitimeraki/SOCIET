"""
Debate API: Async debate simulation with streaming support.
"""
import asyncio
import uuid
from dataclasses import asdict
from typing import Dict, Any, List, Literal, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from src.simulation.debate_config import DebateConfig


router = APIRouter(prefix="/simulate", tags=["debate"])


class DebateConfigRequest(BaseModel):
    """Debate configuration from request."""
    max_agents: int = Field(default=50, ge=1, le=100)
    max_rounds: int = Field(default=5, ge=1, le=20)
    comm_radius: int = Field(default=1, ge=1, le=5)
    min_entity_overlap: int = Field(default=1, ge=1, le=10)
    convergence_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    llm_concurrency: int = Field(default=8, ge=1, le=32)
    topology_score_threshold: float = Field(default=0.15, ge=0.0, le=1.0)


class DebateRequest(BaseModel):
    """Request to start a debate simulation."""
    graph_id: str = Field(default="simulation_runtime", description="Graph/dataset ID")
    query: str = Field(..., description="Debate topic/question")
    selected_domains: List[str] = Field(
        default_factory=list, description="Domain filter, also carried into the intent fallback"
    )
    simulation_depth: Literal["shallow", "standard", "deep"] = Field(
        default="standard",
        description="Depth gate (D3): shallow skips S5 persona distillation; standard/deep run it.",
    )
    config: DebateConfigRequest = Field(default_factory=DebateConfigRequest)


class DebateJobResponse(BaseModel):
    """Response when starting a debate job."""
    job_id: str
    status: str = "queued"


class DebateStatusResponse(BaseModel):
    """Response for debate status check."""
    job_id: str
    status: str  # queued, running, complete, failed
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class RoundStreamEvent(BaseModel):
    """WebSocket event for a single debate round."""
    round: int
    pairs: list[Dict[str, Any]]
    turns: list[Dict[str, Any]]


class DebateStreamComplete(BaseModel):
    """WebSocket event when debate is complete."""
    complete: bool = True
    converged: bool
    verdict: str
    final_stances: Dict[str, str]
    warnings: list[str]


# In-memory job storage
_DEBATE_JOBS: Dict[str, Dict[str, Any]] = {}
_DEBATE_JOBS_LOCK = asyncio.Lock()


def _job_to_status_response(job_id: str, job: Dict[str, Any]) -> DebateStatusResponse:
    """Convert job dict to status response."""
    return DebateStatusResponse(
        job_id=job_id,
        status=job.get("status", "unknown"),
        result=job.get("result"),
        error=job.get("error"),
    )


async def _run_debate_async(
    job_id: str,
    query: str,
    graph_id: str,
    config: DebateConfig,
    selected_domains: Optional[List[str]] = None,
    simulation_depth: str = "standard",
) -> None:
    """Background task to run debate and stream results via WebSocket."""
    # Reuse the manager the job already holds: a client that connected before
    # the task started created and stored one (`stream_debate`), and replacing
    # it would silently drop that client from the S9 stage-event stream.
    ws_manager = (_DEBATE_JOBS.get(job_id) or {}).get("ws_manager") or _DebateWSManager()

    # D3: the depth gate — distillation is on for standard/deep, off for shallow.
    distill = simulation_depth in {"standard", "deep"}

    try:
        async with _DEBATE_JOBS_LOCK:
            _DEBATE_JOBS[job_id]["status"] = "running"
            _DEBATE_JOBS[job_id]["ws_manager"] = ws_manager

        # S3 intent extraction: once per run, before the debate starts. Never
        # raises — on an LLM failure `expand_user_query` yields the deterministic
        # fallback, so a provider outage cannot block the debate.
        from src.llm.client import LLMClient
        from src.utils.queryIntend import FALLBACK_EXTRACTION_CONFIDENCE, QueryIntend

        llm = LLMClient()
        intent = await QueryIntend(client=llm).expand_user_query(
            query, selected_domains=selected_domains
        )
        await ws_manager.broadcast({"type": "intent", "intent": intent.model_dump()})

        # Create GraphContext with proper signature
        from src.persona.graph_context import GraphContext
        from src.graph.config_graph import GraphConfig
        cfg = GraphConfig()

        async with GraphContext(cfg) as ctx:
            # Create orchestrator with all 5 dependencies
            from src.persona.repository import PersonaRepository
            from src.simulation.orchestrator import DebateOrchestrator
            from src.simulation.profile_synthesizer import ProfileSynthesizer
            from src.simulation.topology import CommunicationTopology
            from src.simulation.llm_batch import BatchedLLMRunner
            from src.simulation.verdict import VerdictSynthesizer
            from src.simulation.society_memory import SocietyMemory

            llm_runner = BatchedLLMRunner(llm, concurrency=config.llm_concurrency)

            orchestrator = DebateOrchestrator(
                profile_synthesizer=ProfileSynthesizer(PersonaRepository(
                    neo4j_uri=cfg.neo4j_uri,
                    neo4j_user=cfg.neo4j_username,
                    neo4j_password=cfg.neo4j_password,
                    neo4j_database=cfg.neo4j_database,
                    llm_client=llm,
                ), ctx),
                topology=CommunicationTopology(ctx._driver, ctx._db),
                llm_runner=llm_runner,
                verdict_synthesizer=VerdictSynthesizer(),
                society_memory=SocietyMemory(ctx._driver, ctx._db),
            )

            # Run debate with orchestrator. The S9 stage emitter is the job's
            # own WS manager: real transitions, pushed alongside round events.
            result = await orchestrator.run(
                query=query,
                dataset_id=graph_id,
                config=config,
                ws_broadcast=ws_manager.broadcast,
                on_stage=ws_manager.broadcast,
                intent=intent,
                distill=distill,
            )

        # S9: this layer owns the intent extraction, so it reports the
        # degradation the run cannot see (the fallback intent is a valid
        # object — only `extraction_confidence` tells them apart). Still logged
        # by QueryIntend.fallback_intent; here it reaches the delivered payload.
        if intent is not None and intent.extraction_confidence == FALLBACK_EXTRACTION_CONFIDENCE:
            result.warnings.append(
                "S3 intent: extraction failed — the deterministic fallback intent "
                f"was used (extraction_confidence={FALLBACK_EXTRACTION_CONFIDENCE})."
            )

        # Store result
        async with _DEBATE_JOBS_LOCK:
            _DEBATE_JOBS[job_id]["status"] = "complete"
            _DEBATE_JOBS[job_id]["result"] = {
                "converged": result.converged,
                "verdict": result.verdict,
                "final_stances": result.final_stances,
                "warnings": result.warnings,
                "rounds_executed": result.rounds_executed,
                "intent": result.intent.model_dump() if result.intent else None,
                # S4 decomposition, rendered field-by-field so later additions
                # (e.g. P2-B's provenance anchor) flow through automatically.
                "selection": [asdict(row) for row in result.selection_rows],
                "confidence_score": result.confidence_score,
                "cluster_details": result.cluster_details,
                "supporting_entities": result.supporting_entities,
                "opposing_entities": result.opposing_entities,
            }

        # Send completion event (the verdict fields ride along — §12.3 item 5)
        await ws_manager.broadcast({
            "type": "complete",
            "converged": result.converged,
            "verdict": result.verdict,
            "final_stances": result.final_stances,
            "warnings": result.warnings,
            "rounds_executed": result.rounds_executed,
            "confidence_score": result.confidence_score,
            "cluster_details": result.cluster_details,
            "supporting_entities": result.supporting_entities,
            "opposing_entities": result.opposing_entities,
        })

    except Exception as exc:
        async with _DEBATE_JOBS_LOCK:
            _DEBATE_JOBS[job_id]["status"] = "failed"
            _DEBATE_JOBS[job_id]["error"] = str(exc)

        await ws_manager.broadcast({
            "type": "error",
            "error": str(exc),
        })


class _DebateWSManager:
    """Manages WebSocket connections for debate streaming.

    Keeps the full per-job event buffer so a (re)connecting client replays the
    run from the start (§12.5) — reconnect and mid-run joins are deterministic.
    """

    def __init__(self):
        self.connections: list[WebSocket] = []
        self.buffer: list[Dict[str, Any]] = []
        self._lock = asyncio.Lock()

    async def add(self, ws: WebSocket):
        async with self._lock:
            self.connections.append(ws)

    async def remove(self, ws: WebSocket):
        async with self._lock:
            if ws in self.connections:
                self.connections.remove(ws)

    async def attach(self, ws: WebSocket):
        """Replay the buffer, then subscribe — atomic with respect to broadcasts."""
        async with self._lock:
            for event in self.buffer:
                try:
                    await ws.send_json(event)
                except Exception:
                    return
            self.connections.append(ws)

    async def broadcast(self, data: Dict[str, Any]):
        async with self._lock:
            self.buffer.append(data)
            connections = list(self.connections)

        for ws in connections:
            try:
                await ws.send_json(data)
            except Exception:
                pass  # Client disconnected


@router.post("/debate", response_model=DebateJobResponse, status_code=202)
async def create_debate(request: DebateRequest):
    """
    Start a new debate simulation.

    Returns a job_id for polling status or WebSocket streaming.
    """
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="query is required")

    job_id = str(uuid.uuid4())
    config = DebateConfig(
        max_agents=request.config.max_agents,
        max_rounds=request.config.max_rounds,
        comm_radius=request.config.comm_radius,
        min_entity_overlap=request.config.min_entity_overlap,
        convergence_threshold=request.config.convergence_threshold,
        llm_concurrency=request.config.llm_concurrency,
        topology_score_threshold=request.config.topology_score_threshold,
    )

    async with _DEBATE_JOBS_LOCK:
        _DEBATE_JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "query": request.query,
            "graph_id": request.graph_id,
            "config": asdict(config),
            "result": None,
            "error": None,
        }

    # Start background task
    asyncio.create_task(_run_debate_async(
        job_id=job_id,
        query=request.query,
        graph_id=request.graph_id,
        config=config,
        selected_domains=request.selected_domains,
        simulation_depth=request.simulation_depth,
    ))

    return DebateJobResponse(job_id=job_id, status="queued")


@router.get("/{job_id}", response_model=DebateStatusResponse)
async def get_debate_status(job_id: str):
    """
    Get debate simulation status and result.
    """
    async with _DEBATE_JOBS_LOCK:
        job = _DEBATE_JOBS.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return _job_to_status_response(job_id, job)


@router.websocket("/{job_id}/stream")
async def stream_debate(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint to stream debate rounds in real-time.
    """
    # Verify job exists
    async with _DEBATE_JOBS_LOCK:
        job = _DEBATE_JOBS.get(job_id)
        if not job:
            await websocket.close(code=4004, reason="Job not found")
            return

        ws_manager = job.get("ws_manager")
        if ws_manager is None:
            # Job not started yet, create a new manager. The outer lock is
            # already held here, so this write is atomic without re-taking it.
            ws_manager = _DebateWSManager()
            if "ws_manager" not in _DEBATE_JOBS[job_id]:
                _DEBATE_JOBS[job_id]["ws_manager"] = ws_manager

    await websocket.accept()
    await ws_manager.attach(websocket)

    try:
        # Keep connection alive and relay messages
        while True:
            try:
                # Wait for messages (mainly to detect disconnection)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
                # Echo back as acknowledgment
                await websocket.send_json({"type": "ack", "data": data})
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "ping"})

    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.remove(websocket)
