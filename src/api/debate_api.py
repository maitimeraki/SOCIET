"""
Debate API: Async debate simulation with streaming support.
"""
import asyncio
import uuid
import json
from dataclasses import asdict
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from src.simulation.debate_config import DebateConfig
from src.simulation.graph_debate_engine import (
    DebateEngine,
    DebateResult,
    RoundResult,
    AgentTurn,
    DebateVerdict,
    Stance,
)
from src.simulation.agent_node import AgentNode
from src.simulation.agent_spawner import AgentSpawner
from src.simulation.communication_graph import CommunicationGraph, CommPair


router = APIRouter(prefix="/simulate", tags=["debate"])


class DebateConfigRequest(BaseModel):
    """Debate configuration from request."""
    max_agents: int = Field(default=50, ge=1, le=100)
    max_rounds: int = Field(default=5, ge=1, le=20)
    comm_radius: int = Field(default=1, ge=1, le=5)
    min_entity_overlap: int = Field(default=1, ge=1, le=10)
    convergence_threshold: float = Field(default=0.8, ge=0.0, le=1.0)


class DebateRequest(BaseModel):
    """Request to start a debate simulation."""
    graph_id: str = Field(default="simulation_runtime", description="Graph/dataset ID")
    query: str = Field(..., description="Debate topic/question")
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
) -> None:
    """Background task to run debate and stream results via WebSocket."""
    ws_manager = _DebateWSManager()

    try:
        async with _DEBATE_JOBS_LOCK:
            _DEBATE_JOBS[job_id]["status"] = "running"
            _DEBATE_JOBS[job_id]["ws_manager"] = ws_manager

        # Create debate engine with GraphContext
        from src.persona.graph_context import GraphContext
        from src.graph.config_graph import GraphConfig
        cfg = GraphConfig()
        async with GraphContext(
            neo4j_uri=cfg.neo4j_uri,
            neo4j_user=cfg.neo4j_username,
            neo4j_password=cfg.neo4j_password,
            neo4j_database=cfg.neo4j_database,
        ) as ctx:
            spawner = AgentSpawner(graph_context=ctx)
            comm_graph = CommunicationGraph()
            engine = DebateEngine(spawner=spawner, comm_graph=comm_graph)

            # Run debate with streaming
            result = await _run_debate_with_streaming(
                engine=engine,
                query=query,
                config=config,
                ws_manager=ws_manager,
            )

        # Store result
        async with _DEBATE_JOBS_LOCK:
            _DEBATE_JOBS[job_id]["status"] = "complete"
            _DEBATE_JOBS[job_id]["result"] = _debate_result_to_dict(result)

        # Send completion event
        await ws_manager.broadcast({
            "type": "complete",
            "converged": result.converged,
            "verdict": result.verdict,
            "final_stances": result.final_stances,
            "warnings": result.warnings,
        })

    except Exception as exc:
        async with _DEBATE_JOBS_LOCK:
            _DEBATE_JOBS[job_id]["status"] = "failed"
            _DEBATE_JOBS[job_id]["error"] = str(exc)

        await ws_manager.broadcast({
            "type": "error",
            "error": str(exc),
        })


async def _run_debate_with_streaming(
    engine: DebateEngine,
    query: str,
    config: DebateConfig,
    ws_manager: "_DebateWSManager",
) -> DebateResult:
    """Run debate with WebSocket streaming after each round."""
    # Spawn agents from query
    agents = await engine.spawner.spawn_agents_from_query(
        query=query,
        max_agents=config.max_agents,
    )

    if not agents:
        return DebateResult(
            query=query,
            rounds=[],
            converged=False,
            final_stances={},
            verdict="No agents could be spawned for this query.",
            warnings=["No relevant entities found for query"],
        )

    # Compute initial pairs
    pairs = engine.comm_graph.compute_pairs(
        agents=agents,
        threshold=config.min_entity_overlap,
    )

    # Initialize state
    debate_history: list[Dict[str, Any]] = []
    rounds: list[RoundResult] = []
    warnings: list[str] = []

    # Run rounds
    for round_num in range(1, config.max_rounds + 1):
        # Get pairs for this round
        round_pairs = engine.comm_graph.get_round_pairs(
            agents=agents,
            round_num=round_num,
            config=config,
        )

        # Execute round
        try:
            round_result = await engine._run_round(
                agents=agents,
                pairs=round_pairs,
                round_num=round_num,
                query=query,
                history=debate_history,
            )
            rounds.append(round_result)

            # Update history
            for turn in round_result.turns:
                debate_history.append({
                    "agent_name": turn.agent_name,
                    "agent_id": turn.agent_id,
                    "content": turn.content,
                    "stance": turn.stance,
                    "confidence": turn.confidence,
                    "round": round_num,
                })

            # Stream round result via WebSocket
            await ws_manager.broadcast({
                "type": "round",
                "round": round_num,
                "pairs": [_comm_pair_to_dict(p) for p in round_result.pairs],
                "turns": [_agent_turn_to_dict(t) for t in round_result.turns],
            })

            # Check convergence
            if engine._check_convergence([r.turns for r in rounds]):
                break

        except Exception as exc:
            warnings.append(f"Round {round_num} failed: {exc}")
            continue

    # Generate verdict
    verdict = engine._generate_verdict(rounds, agents)

    # Collect final stances
    final_stances = {}
    for agent in agents:
        stance_key = str(agent.id)
        for round_result in reversed(rounds):
            for turn in round_result.turns:
                if turn.agent_id == stance_key:
                    final_stances[agent.name] = turn.stance
                    break
            if agent.name in final_stances:
                break
        else:
            final_stances[agent.name] = engine._get_stance_value(agent.stance)

    return DebateResult(
        query=query,
        rounds=rounds,
        converged=engine._check_convergence([r.turns for r in rounds]),
        final_stances=final_stances,
        verdict=verdict,
        warnings=warnings,
    )


class _DebateWSManager:
    """Manages WebSocket connections for debate streaming."""

    def __init__(self):
        self.connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def add(self, ws: WebSocket):
        async with self._lock:
            self.connections.append(ws)

    async def remove(self, ws: WebSocket):
        async with self._lock:
            if ws in self.connections:
                self.connections.remove(ws)

    async def broadcast(self, data: Dict[str, Any]):
        async with self._lock:
            connections = list(self.connections)

        for ws in connections:
            try:
                await ws.send_json(data)
            except Exception:
                pass  # Client disconnected


_WS_MANAGERS: Dict[str, _DebateWSManager] = {}


def _comm_pair_to_dict(pair: CommPair) -> Dict[str, Any]:
    return {
        "agent_a": pair.agent_a,
        "agent_b": pair.agent_b,
        "shared_entities": pair.shared_entities,
        "evidence": pair.evidence,
    }


def _agent_turn_to_dict(turn: AgentTurn) -> Dict[str, Any]:
    return {
        "agent_id": turn.agent_id,
        "agent_name": turn.agent_name,
        "content": turn.content,
        "stance": turn.stance,
        "confidence": turn.confidence,
        "references": turn.references,
    }


def _debate_result_to_dict(result: DebateResult) -> Dict[str, Any]:
    return {
        "query": result.query,
        "rounds": [
            {
                "round_num": r.round_num,
                "turns": [_agent_turn_to_dict(t) for t in r.turns],
                "pairs": [_comm_pair_to_dict(p) for p in r.pairs],
            }
            for r in result.rounds
        ],
        "converged": result.converged,
        "final_stances": result.final_stances,
        "verdict": result.verdict,
        "warnings": result.warnings,
    }


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
            # Job not started yet, create a new manager
            ws_manager = _DebateWSManager()
            async with _DEBATE_JOBS_LOCK:
                if "ws_manager" not in _DEBATE_JOBS[job_id]:
                    _DEBATE_JOBS[job_id]["ws_manager"] = ws_manager

    await websocket.accept()
    await ws_manager.add(websocket)

    try:
        # Send current status if job already has results
        async with _DEBATE_JOBS_LOCK:
            current_job = _DEBATE_JOBS.get(job_id)
            if current_job:
                if current_job["status"] == "complete" and current_job.get("result"):
                    await websocket.send_json({
                        "type": "complete",
                        "converged": current_job["result"].get("converged", False),
                        "verdict": current_job["result"].get("verdict", ""),
                        "final_stances": current_job["result"].get("final_stances", {}),
                        "warnings": current_job["result"].get("warnings", []),
                    })
                elif current_job["status"] == "failed":
                    await websocket.send_json({
                        "type": "error",
                        "error": current_job.get("error", "Unknown error"),
                    })

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
