"""
Debate API: Async debate simulation with streaming support.
"""
import asyncio
import logging
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Dict, Any, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from src.api import run_doc
from src.api.limits import limiter, service_available
from src.auth.deps import current_user, require_owner, websocket_user
from src.config.settings import get_settings
from src.db.models import User
from src.simulation.debate_config import DebateConfig


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulate", tags=["debate"])


class DebateConfigRequest(BaseModel):
    """Debate configuration from request."""
    max_agents: int = Field(default=50, ge=1, le=100)
    max_rounds: int = Field(default=5, ge=1, le=20)
    comm_radius: int = Field(default=1, ge=1, le=5)
    min_entity_overlap: int = Field(default=1, ge=1, le=10)
    max_pairs_per_round: int = Field(default=50, ge=1, le=200)
    convergence_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    llm_concurrency: int = Field(default=8, ge=1, le=32)
    topology_score_threshold: float = Field(default=0.15, ge=0.0, le=1.0)
    max_new_agents_per_round: int = Field(default=2, ge=0, le=10)
    snapshot_top_k: int = Field(default=8, ge=5, le=20)


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
    context: Optional[dict] = Field(
        default=None,
        description="User-supplied scenario constraints; weighed into the synthesized verdict.",
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


# In-process working state for live runs: the WebSocket managers and the
# handoff between the run task and the routes. NOT the truth — rows are
# (`run_doc`); every read below goes to the database.
_DEBATE_JOBS: Dict[str, Dict[str, Any]] = {}
_DEBATE_JOBS_LOCK = asyncio.Lock()


def _job_doc(job: dict) -> dict:
    """The doc shape of a live job, for the row write."""
    return {
        "run_id": job.get("job_id"),
        "user_id": job.get("user_id"),
        "created_at": job.get("created_at"),
        "query": job.get("query"),
        "dataset_id": job.get("graph_id"),
        "config": job.get("config"),
        "status": job.get("status"),
        "events": [],
        "result": job.get("result"),
        "error": job.get("error"),
    }


async def _run_debate_async(
    job_id: str,
    query: str,
    graph_id: str,
    config: DebateConfig,
    selected_domains: Optional[List[str]] = None,
    simulation_depth: str = "standard",
    context: Optional[dict] = None,
) -> None:
    """Background task to run debate and stream results via WebSocket."""
    # Reuse the manager the job already holds: a client that connected before
    # the task started created and stored one (`stream_debate`), and replacing
    # it would silently drop that client from the S9 stage-event stream.
    ws_manager = (_DEBATE_JOBS.get(job_id) or {}).get("ws_manager") or _DebateWSManager(job_id=job_id)

    # D3: the depth gate — distillation is on for standard/deep, off for shallow.
    distill = simulation_depth in {"standard", "deep"}

    try:
        async with _DEBATE_JOBS_LOCK:
            _DEBATE_JOBS[job_id]["status"] = "running"
            _DEBATE_JOBS[job_id]["ws_manager"] = ws_manager

        await _persist_debate_run(job_id)  # written at job start, events empty (§12.4)

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
                llm_client=llm,
                on_stage=ws_manager.broadcast,
                intent=intent,
                distill=distill,
                context=context,
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
                "narrative": result.narrative,
                "final_stances": result.final_stances,
                "warnings": result.warnings,
                "rounds_executed": result.rounds_executed,
                "intent": result.intent.model_dump() if result.intent else None,
                # S4 decomposition, rendered field-by-field so later additions
                # (e.g. P2-B's provenance anchor) flow through automatically.
                "selection": [asdict(row) for row in result.selection_rows],
                "confidence_score": result.confidence_score,
                "weight_share": result.weight_share,
                "contested": result.contested,
                "provenance_by_claim": result.provenance_by_claim,
                "cluster_details": result.cluster_details,
                "supporting_entities": result.supporting_entities,
                "opposing_entities": result.opposing_entities,
                "dissenting_views": result.dissenting_views,
                "evidence": result.evidence,
            }

        # Send completion event (the verdict fields ride along — §12.3 item 5)
        await ws_manager.broadcast({
            "type": "complete",
            "converged": result.converged,
            "verdict": result.verdict,
            "narrative": result.narrative,
            "final_stances": result.final_stances,
            "warnings": result.warnings,
            "rounds_executed": result.rounds_executed,
            "confidence_score": result.confidence_score,
            "weight_share": result.weight_share,
            "contested": result.contested,
            "provenance_by_claim": result.provenance_by_claim,
            "cluster_details": result.cluster_details,
            "supporting_entities": result.supporting_entities,
            "opposing_entities": result.opposing_entities,
            "dissenting_views": result.dissenting_views,
            "evidence": result.evidence,
        })

    except Exception as exc:
        # A raise on the orchestrator's not-debatable paths carries the run's
        # accumulated warnings; surface them with the error (broadcast → buffered
        # → persisted) so a failed run does not lose its diagnostics.
        warnings = list(getattr(exc, "warnings", []) or [])
        async with _DEBATE_JOBS_LOCK:
            _DEBATE_JOBS[job_id]["status"] = "failed"
            _DEBATE_JOBS[job_id]["error"] = str(exc)

        await ws_manager.broadcast({
            "type": "error",
            "error": str(exc),
            "warnings": warnings,
        })


class _DebateWSManager:
    """Manages WebSocket connections for debate streaming.

    Keeps the full per-job event buffer so a (re)connecting client replays the
    run from the start (§12.5) — reconnect and mid-run joins are deterministic.
    """

    def __init__(self, job_id: str | None = None):
        self.job_id = job_id
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

        if self.job_id is not None:
            try:
                # Every streamed event is a row — the log is the durable record
                # (§4), so this is not throttled (the head write below is).
                await run_doc.append_run_event(self.job_id, len(self.buffer), data)
                await _persist_debate_run(self.job_id)
            except Exception as exc:
                # Persistence is best-effort by contract: a DB hiccup must not
                # kill the live stream (the failure is logged, never swallowed).
                logger.warning("run event persist failed for %s: %s", self.job_id, exc)

        for ws in connections:
            try:
                await ws.send_json(data)
            except Exception:
                pass  # Client disconnected


# Run-doc persistence throttle: one head write per run per window. The head is
# always written whole, so a skipped transition is carried by the next write —
# write work no longer scales with event count. Keyed per run id; the entry is
# dropped on the terminal write so finished runs leave no state behind.
_PERSIST_MIN_INTERVAL_S = 0.5
_TERMINAL_STATUSES = {"complete", "failed", "cancelled"}
_LAST_PERSIST_AT: Dict[str, float] = {}


async def _persist_debate_run(job_id: str) -> None:
    """Write the live job's head rows (status/result/error) to Postgres.

    The events are rows of their own (appended in `broadcast`); this is the
    head only, throttled to one write per run per `_PERSIST_MIN_INTERVAL_S`
    (monotonic clock). Terminal states bypass the throttle so the final head
    is never stale. Best-effort by contract: a failed write is logged, never
    raised — persistence must not break a live run.
    """
    try:
        job = _DEBATE_JOBS.get(job_id)
        manager = job.get("ws_manager") if job else None
        if not job or manager is None:
            return
        if job.get("status") in _TERMINAL_STATUSES:
            _LAST_PERSIST_AT.pop(job_id, None)
        else:
            now = time.monotonic()
            last = _LAST_PERSIST_AT.get(job_id)
            if last is not None and now - last < _PERSIST_MIN_INTERVAL_S:
                return
            _LAST_PERSIST_AT[job_id] = now
        await run_doc.write_run_doc(_job_doc(job))
    except Exception as exc:
        logger.warning("run doc persist failed for %s: %s", job_id, exc)


@router.post("/debate", response_model=DebateJobResponse, status_code=202)
@limiter.limit(lambda: get_settings().rate_limit_debate_enqueue)
async def create_debate(
    body: DebateRequest,
    request: Request,
    user: User = Depends(current_user),
    _available: None = Depends(service_available),
):
    """
    Start a new debate simulation.

    Returns a job_id for polling status or WebSocket streaming.
    """
    if not body.query or not body.query.strip():
        raise HTTPException(status_code=400, detail="query is required")

    job_id = str(uuid.uuid4())
    config = DebateConfig(
        max_agents=body.config.max_agents,
        max_rounds=body.config.max_rounds,
        comm_radius=body.config.comm_radius,
        min_entity_overlap=body.config.min_entity_overlap,
        max_pairs_per_round=body.config.max_pairs_per_round,
        convergence_threshold=body.config.convergence_threshold,
        llm_concurrency=body.config.llm_concurrency,
        topology_score_threshold=body.config.topology_score_threshold,
        max_new_agents_per_round=body.config.max_new_agents_per_round,
        snapshot_top_k=body.config.snapshot_top_k,
    )

    async with _DEBATE_JOBS_LOCK:
        _DEBATE_JOBS[job_id] = {
            "job_id": job_id,
            "user_id": str(user.id),
            "status": "queued",
            "query": body.query,
            "graph_id": body.graph_id,
            "config": asdict(config),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "result": None,
            "error": None,
        }

    # Durable at accept time: the queued run exists as rows before the 202.
    await run_doc.write_run_doc(_job_doc(_DEBATE_JOBS[job_id]))

    # Start background task
    asyncio.create_task(_run_debate_async(
        job_id=job_id,
        query=body.query,
        graph_id=body.graph_id,
        config=config,
        selected_domains=body.selected_domains,
        simulation_depth=body.simulation_depth,
        context=body.context,
    ))

    return DebateJobResponse(job_id=job_id, status="queued")


@router.get("/debates")
async def list_debates(
    request: Request,
    user: User = Depends(current_user),
    limit: int = Query(25, ge=1, le=100),
    cursor: Optional[str] = None,
):
    """Newest-first run summaries for the history views (§12.4).

    `/api/v1/simulate/debates` is keyset-paginated over ``(created_at, id)``
    DESC (plan §6): ``{items, next_cursor}``. The legacy alias keeps today's
    array shape (R15 deprecation window) — both mounts share this function, so
    the response branches on the request path.
    """
    if request.url.path.startswith("/api/v1"):
        try:
            return await run_doc.list_run_summaries(user.id, limit=limit, cursor=cursor)
        except run_doc.InvalidCursor:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_cursor", "message": "The pagination cursor is not valid."},
            )
    return (await run_doc.list_run_summaries(user.id))["items"]


@router.get("/debates/{run_id}")
async def get_debate_doc(run_id: str, user: User = Depends(current_user)):
    doc = await run_doc.read_run_doc(run_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Run not found")
    await require_owner(doc.get("user_id"), user)
    return doc


@router.get("/{job_id}", response_model=DebateStatusResponse)
async def get_debate_status(job_id: str, user: User = Depends(current_user)):
    """
    Get debate simulation status and result.
    """
    head = await run_doc.read_run_head(job_id)
    if head is None or head.get("kind") != "debate":
        raise HTTPException(status_code=404, detail="Job not found")
    await require_owner(head.get("user_id"), user)

    return DebateStatusResponse(
        job_id=job_id,
        status=head["status"],
        result=head["result"],
        error=head["error"],
    )


@router.websocket("/{job_id}/stream")
async def stream_debate(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint to stream debate rounds in real-time.

    Authenticated before `accept()` (R4): a live sid cookie or a one-time
    ``?ticket=``; then the job must be the caller's. Failures close the
    handshake with a policy code and nothing is ever streamed.
    """
    user = await websocket_user(websocket)
    if user is None:
        await websocket.close(code=4401, reason="Authentication required")
        return

    head = await run_doc.read_run_head(job_id)
    try:
        if head is None or head.get("kind") != "debate":
            raise HTTPException(status_code=404, detail="Not found.")
        await require_owner(head.get("user_id"), user)
    except HTTPException:
        await websocket.close(code=4404, reason="Job not found")
        return

    async with _DEBATE_JOBS_LOCK:
        job = _DEBATE_JOBS.get(job_id)
        if job is None:
            # A row without a live job in this process: nothing to stream.
            await websocket.close(code=4404, reason="Job not found")
            return
        ws_manager = job.get("ws_manager")
        if ws_manager is None:
            # Job not started yet, create a new manager. The lock is already
            # held here, so this write is atomic without re-taking it.
            ws_manager = _DebateWSManager(job_id=job_id)
            job["ws_manager"] = ws_manager

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
