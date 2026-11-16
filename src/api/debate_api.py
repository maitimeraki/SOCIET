"""
Debate API: Async debate simulation with streaming support.
"""

import asyncio
import json
import logging
import math
import re
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Literal, Mapping, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.api import run_doc
from src.api.errors import payment_required
from src.api.graph_snapshot import read_snapshot as read_graph_snapshot
from src.api.jobs_api import enqueue_or_http
from src.api.limits import limiter, service_available
from src.api.public_events import (
    METERING_STOPPED_MESSAGE,
    RUN_FAILED_MESSAGE,
    project_event,
    project_result,
    stored_result,
)
from src.audit import client_ip
from src.audit import record as audit_record
from src.auth.cookies import verify_csrf
from src.auth.deps import (
    current_user,
    require_owned_dataset,
    require_owner,
    websocket_user,
)
from src.billing import units as billing_units
from src.billing.entitlements import resolve_entitlements
from src.billing.metering import MeteringError
from src.config.settings import get_settings
from src.db.engine import get_db
from src.db.models import User
from src.llm.config_llm import get_llm_config
from src.simulation.actor_filter import ACTOR_BATCH, TOKENS_PER_LABEL
from src.simulation.agent_record import AgentView
from src.simulation.debate_config import DebateConfig
from src.simulation.evidence import MAX_ITEM_CHARS
from src.simulation.profile_generator import (
    CALLS_PER_DRAW,
    EXPECTED_CALLS_PER_SEAT,
    JUDGE_MAX_TOKENS,
    REJECTED_DRAW_CALLS,
    prompt_char_bound,
    typical_prompt_chars,
)
from src.simulation.profile_synthesizer import DRAW_SLACK, POOL_CAP
from src.simulation.report_retry import (
    REFUSAL_IN_FLIGHT,
    REFUSAL_MESSAGES,
    retry_refusal,
)
from src.simulation.verdict import REPORT_MAX_ATTEMPTS
from src.utils.labels import public_source

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/simulate", tags=["debate"], dependencies=[Depends(verify_csrf)]
)


class DebateConfigRequest(BaseModel):
    """Debate configuration from request."""

    max_agents: int = Field(default=8, ge=1, le=12)
    max_rounds: int = Field(default=5, ge=1, le=20)
    comm_radius: int = Field(default=1, ge=1, le=5)
    min_entity_overlap: int = Field(default=1, ge=1, le=10)
    max_pairs_per_round: int = Field(default=50, ge=1, le=200)
    convergence_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    llm_concurrency: int = Field(default=8, ge=1, le=32)
    topology_score_threshold: float = Field(default=0.15, ge=0.0, le=1.0)
    max_new_agents_per_round: int = Field(default=2, ge=0, le=10)
    snapshot_top_k: int = Field(default=8, ge=5, le=20)


#: The serialised size cap on the user's scenario context (audit L-G1).
CONTEXT_MAX_BYTES = 4096


class DebateRequest(BaseModel):
    """Request to start a debate simulation."""

    graph_id: uuid.UUID = Field(..., description="The owned corpus (dataset) id")
    query: str = Field(..., description="Debate topic/question")
    corpus_label: Optional[str] = Field(
        default=None,
        max_length=120,
        description="The wizard's client-side corpus name, for the history list.",
    )
    selected_domains: List[str] = Field(
        default_factory=list,
        description="Domain filter, also carried into the intent fallback",
    )
    simulation_depth: Literal["shallow", "standard", "deep"] = Field(
        default="standard",
        description="Accepted for client compatibility; it currently has no effect on the run.",
    )
    context: Optional[dict] = Field(
        default=None,
        description="User-supplied scenario constraints; weighed into the synthesized verdict.",
    )
    config: DebateConfigRequest = Field(default_factory=DebateConfigRequest)

    @field_validator("context")
    @classmethod
    def _cap_context(cls, value: Optional[dict]) -> Optional[dict]:
        if value is None:
            return value
        # json.dumps escapes non-ASCII (ensure_ascii), so this measures at least the UTF-8 length.
        size = len(json.dumps(value, default=str).encode("utf-8"))
        if size > CONTEXT_MAX_BYTES:
            raise ValueError(f"context is {size} bytes; the limit is {CONTEXT_MAX_BYTES}")
        return value


class DebateJobResponse(BaseModel):
    """Response when starting a debate job."""

    job_id: str
    status: str = "queued"


class VerdictRetryResponse(BaseModel):
    """The accepted verdict retry: its job (poll /api/v1/jobs/{job_id}) and the run whose report it rewrites."""

    job_id: str
    run_id: str
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
        "corpus_label": job.get("corpus_label"),
        "config": job.get("config"),
        "status": job.get("status"),
        "events": [],
        "result": stored_result(job.get("result")),
        "error": job.get("error"),
    }


async def _ensure_live_job(job_id: str) -> dict:
    """The live entry for a job this process did not create, seeded from its rows.

    The worker runs the task in its own process, where the dict is empty; the
    rows are the truth, so the live entry is rebuilt from them rather than
    assumed present.
    """
    doc = await run_doc.read_run_doc(job_id)
    if doc is None:
        return {}
    return {
        "job_id": job_id,
        "user_id": doc.get("user_id"),
        "status": doc.get("status") or "queued",
        "query": doc.get("query"),
        "graph_id": doc.get("dataset_id"),
        "corpus_label": doc.get("corpus_label"),
        "config": doc.get("config") or {},
        "created_at": doc.get("created_at"),
        "result": doc.get("result"),
        "error": doc.get("error"),
    }


#: Units one typical debate call settles: the typical prompt at four characters per token, plus the
#: profile completion cap, rounded up per call as units.py settles it. Typical prompt = the larger of
#: the profile and judge prompts at the caps (typical_prompt_chars). This sizes the hold.
UNITS_PER_CALL_TYPICAL = billing_units.units_for_tokens(
    math.ceil(typical_prompt_chars() / 4), get_llm_config().profile_max_tokens
)


def debate_worst_call_units() -> int:
    """Units one debate call settles at most: prompt_char_bound() characters (one token each) plus the
    largest completion cap. Used only for the first-attempt bound in debate_worst_case_units, never for the hold."""
    cfg = get_llm_config()
    max_completion = max(
        cfg.profile_max_tokens,
        cfg.verdict_max_tokens,
        cfg.max_output_tokens,
        JUDGE_MAX_TOKENS,
        TOKENS_PER_LABEL * ACTOR_BATCH,
    )
    return billing_units.units_for_tokens(prompt_char_bound(), max_completion)


def debate_worst_case_units(*, agents: int, rounds: int, max_new_per_round: int, max_pairs_per_round: int) -> int:
    """An estimate bound over first attempts, pinned by a test. It is not a ceiling over retries: a
    malformed turn is re-asked once and those retries are not counted here, so a run whose turns retry
    can settle above this figure. It is conditional: the profile and judge prompts are bounded in code
    (prompt_char_bound), but round, verdict, intent and actor classification prompts are NOT
    byte-bounded in code. Charging them the same per-call bound is an assumption, so the bound holds
    only if those prompts stay within prompt_char_bound(). It is documented for the record and is not
    the admission reserve.

    Calls counted at their caps, one attempt per turn: intent (1); the pool's actor classification (one call per
    ACTOR_BATCH labels, the pool keeps at most POOL_CAP candidates); report attempts (REPORT_MAX_ATTEMPTS);
    the roster's draws, at most (agents + DRAW_SLACK) x CALLS_PER_DRAW; per round, activation's
    classification and its joiner draws; and per round two turns per pair, pairs capped by the request
    and by agents choose 2. Each call charged debate_worst_call_units(). Overruns of the hold are
    charged by settlement (units.py), not by this figure.
    """
    per_round_activation = (
        math.ceil(max_new_per_round / ACTOR_BATCH) + (max_new_per_round + DRAW_SLACK) * CALLS_PER_DRAW
        if max_new_per_round > 0
        else 0
    )
    turns_per_round = 2 * min(max_pairs_per_round, agents * (agents - 1) // 2)
    calls = (
        1
        + math.ceil(POOL_CAP / ACTOR_BATCH)
        + REPORT_MAX_ATTEMPTS
        + (agents + DRAW_SLACK) * CALLS_PER_DRAW
        + rounds * (per_round_activation + turns_per_round)
    )
    return calls * debate_worst_call_units()


def debate_reserve_units(*, agents: int, rounds: int, max_new_per_round: int, max_pairs_per_round: int) -> int:
    """The hold a debate reserves at admission: the expected call count times UNITS_PER_CALL_TYPICAL.

    Expected calls: intent, actor classification and the verdict (one each); per seat its profile and
    judge calls (EXPECTED_CALLS_PER_SEAT); the draw slack's rejections (DRAW_SLACK draws at
    REJECTED_DRAW_CALLS); per round, activation's classification and its joiners (max_new at
    EXPECTED_CALLS_PER_SEAT, plus the same rejection allowance); and rounds x 2 turns per pair. An
    overrun is settled and charged to the period as usual (units.py); the run stops at plan exhaustion. Turn retries are not in the expected count: a malformed turn is re-asked once, so a run that retries can settle above this hold, and that overrun is charged to units_used as settled.
    """
    rejections = DRAW_SLACK * REJECTED_DRAW_CALLS
    per_round_activation = (
        1 + max_new_per_round * EXPECTED_CALLS_PER_SEAT + rejections if max_new_per_round > 0 else 0
    )
    calls = (
        3
        + agents * EXPECTED_CALLS_PER_SEAT
        + rejections
        + rounds * per_round_activation
        + rounds * 2 * max_pairs_per_round
    )
    return calls * UNITS_PER_CALL_TYPICAL


def _job_result(result, *, intent: Optional[dict], retry_inputs: Optional[dict]) -> dict:
    """The stored result of a finished debate or verdict retry.

    The served verdict payload, the intent, and the backend-only retry inputs (kept by stored_result,
    never served). The `complete` event carries the verdict payload alone.
    """
    kept = {"retry_inputs": retry_inputs} if retry_inputs is not None else {}
    return {**_verdict_payload(result), "intent": intent, **kept}


def _verdict_payload(result) -> dict:
    """The verdict fields of a finished run: the job result and the `complete` event share them."""
    return {
        "converged": result.converged,
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
        **result.report,
    }


async def _run_debate_async(
    job_id: str,
    query: str,
    graph_id: str,
    config: DebateConfig,
    selected_domains: Optional[List[str]] = None,
    simulation_depth: str = "standard",
    context: Optional[dict] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> None:
    """Background task to run debate and stream results via WebSocket."""
    from src.simulation.orchestrator import DebateCancelled, SocietyNotDebatableError
    from src.simulation.ranking import NoAgentsDerivableError

    # Reuse the manager the job already holds: a client that connected before
    # the task started created and stored one (`stream_debate`), and replacing
    # it would silently drop that client from the S9 stage-event stream.
    ws_manager = (_DEBATE_JOBS.get(job_id) or {}).get("ws_manager") or _DebateWSManager(
        job_id=job_id
    )

    try:
        async with _DEBATE_JOBS_LOCK:
            job = _DEBATE_JOBS.get(job_id)
            if job is None:
                job = _DEBATE_JOBS[job_id] = await _ensure_live_job(job_id)
            job["status"] = "running"
            job["ws_manager"] = ws_manager

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
        await ws_manager.broadcast(
            {"type": "intent", "intent": intent.model_dump() if intent else None}
        )

        # Create GraphContext with proper signature
        from src.graph.config_graph import GraphConfig
        from src.persona.graph_context import GraphContext

        cfg = GraphConfig()

        async with GraphContext(cfg) as ctx:
            # Create orchestrator with all 5 dependencies
            from src.persona.repository import PersonaRepository
            from src.simulation.llm_batch import BatchedLLMRunner
            from src.simulation.orchestrator import DebateOrchestrator
            from src.simulation.profile_synthesizer import ProfileSynthesizer
            from src.simulation.society_memory import SocietyMemory
            from src.simulation.topology import CommunicationTopology
            from src.simulation.verdict import VerdictSynthesizer

            llm_runner = BatchedLLMRunner(llm, concurrency=config.llm_concurrency)

            orchestrator = DebateOrchestrator(
                profile_synthesizer=ProfileSynthesizer(
                    PersonaRepository(
                        neo4j_uri=cfg.neo4j_uri,
                        neo4j_user=cfg.neo4j_username,
                        neo4j_password=cfg.neo4j_password,
                        neo4j_database=cfg.neo4j_database,
                        llm_client=llm,
                    ),
                    ctx,
                ),
                topology=CommunicationTopology(ctx._driver, ctx._db),
                llm_runner=llm_runner,
                verdict_synthesizer=VerdictSynthesizer(),
                society_memory=SocietyMemory(ctx._driver, ctx._db),
            )

            # Seat decisions: the caller-owned sink the seated set is read from.
            seat_decisions: list = []

            # Agent records are stored at each synthesis boundary (initial seats, then each
            # joiner batch), so a debate that stops later still keeps them.
            records_stored = True

            async def _store_agent_records(batch: list) -> None:
                nonlocal records_stored
                if not await _persist_agent_records(job_id, batch):
                    records_stored = False

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
                context=context,
                cancel_check=cancel_check,
                decisions=seat_decisions,
                on_records=_store_agent_records,
            )
            if not records_stored:
                result.warnings.append(AGENT_RECORDS_NOT_STORED)

        # S9: this layer owns the intent extraction, so it reports the
        # degradation the run cannot see (the fallback intent is a valid
        # object — only `extraction_confidence` tells them apart). Still logged
        # by QueryIntend.fallback_intent; here it reaches the delivered payload.
        if (
            intent is not None
            and intent.extraction_confidence == FALLBACK_EXTRACTION_CONFIDENCE
        ):
            result.warnings.append(
                "S3 intent: extraction failed — the deterministic fallback intent "
                f"was used (extraction_confidence={FALLBACK_EXTRACTION_CONFIDENCE})."
            )

        # Store result
        async with _DEBATE_JOBS_LOCK:
            _DEBATE_JOBS[job_id]["status"] = "complete"
            _DEBATE_JOBS[job_id]["result"] = _job_result(
                result,
                intent=result.intent.model_dump() if result.intent else None,
                retry_inputs=result.retry_inputs,
            )

        # Send completion event (the verdict fields ride along — §12.3 item 5)
        await ws_manager.broadcast({"type": "complete", **_verdict_payload(result)})

    except DebateCancelled as exc:
        # Cancelled is terminal, not failed: mark the live state and let the
        # raise reach the job boundary, which owns the cancelled row write.
        async with _DEBATE_JOBS_LOCK:
            _DEBATE_JOBS.setdefault(job_id, {})["status"] = "cancelled"
        await ws_manager.broadcast({"type": "cancelled", "error": str(exc)})
        raise

    except Exception as exc:
        # A raise on the orchestrator's not-debatable paths carries the run's
        # accumulated warnings; surface them with the error (broadcast → buffered
        # → persisted) so a failed run does not lose its diagnostics.
        warnings = list(getattr(exc, "warnings", []) or [])
        if isinstance(exc, (SocietyNotDebatableError, NoAgentsDerivableError)):
            # Messages these two are authored for the user.
            message = str(exc)
        elif isinstance(exc, MeteringError):
            # The owner's own billing state: an authored sentence, never the raw reason.
            logger.warning("debate run %s stopped by metering", job_id, exc_info=exc)
            message = METERING_STOPPED_MESSAGE
        else:
            logger.exception("debate run %s failed", job_id)
            message = RUN_FAILED_MESSAGE
        async with _DEBATE_JOBS_LOCK:
            _DEBATE_JOBS.setdefault(job_id, {})["status"] = "failed"
            _DEBATE_JOBS.setdefault(job_id, {})["error"] = message

        await ws_manager.broadcast(
            {
                "type": "error",
                "error": message,
                "warnings": warnings,
            }
        )


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
        data = project_event(data)
        if data is None:
            return
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


# Shown to the user when a run's agent records could not be stored. Generic on purpose:
# the cause is logged server-side, never sent.
AGENT_RECORDS_NOT_STORED = (
    "The agent records for this run could not be stored; its agent roster is unavailable."
)


async def _persist_agent_records(job_id: str, records: list) -> bool:
    """Write a batch of a run's backend-only agent records. True when stored.

    Best-effort, as `_persist_debate_run`: a failed write is logged, never raised, so
    persistence cannot break a live debate. The caller reports a False as a warning.
    """
    try:
        await run_doc.write_agent_records(job_id, records)
        return True
    except Exception:
        logger.exception("agent records write failed for run %s", job_id)
        return False


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
    db: AsyncSession = Depends(get_db),
    _available: None = Depends(service_available),
):
    """
    Start a new debate simulation.

    Returns a job_id for polling status or WebSocket streaming.
    """
    if not body.query or not body.query.strip():
        raise HTTPException(status_code=400, detail="query is required")

    # The corpus becomes a foreign key on the run, so it must be one this caller
    # owns; the run insert then cannot fail on the constraint afterwards.
    await require_owned_dataset(db, user, body.graph_id)

    # The plan is the session user's row, never the body (§4): any plan/units
    # in the request is ignored, and only the plan's caps bound the work.
    ent = await resolve_entitlements(db, user=user)
    requested = body.config
    explicit = requested.model_fields_set
    ip = client_ip(request)

    for field, cap, noun in (
        ("max_agents", ent.plan.max_agents, "agents"),
        ("max_rounds", ent.plan.max_rounds, "rounds"),
    ):
        if field in explicit and getattr(requested, field) > cap:
            await audit_record(
                db,
                "plan_denied",
                user_id=user.id,
                target=None,
                ip=ip,
                meta={
                    "field": field,
                    "requested": getattr(requested, field),
                    "cap": cap,
                },
            )
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "plan_limit_exceeded",
                    "message": f"Your plan allows at most {cap} {noun}.",
                },
            )

    agents = min(requested.max_agents, ent.plan.max_agents)
    rounds = min(requested.max_rounds, ent.plan.max_rounds)
    pairs = min(requested.max_pairs_per_round, agents)
    applied = {
        "max_agents": agents,
        "max_rounds": rounds,
        "max_pairs_per_round": pairs,
    }
    requested_values = {
        "max_agents": requested.max_agents,
        "max_rounds": requested.max_rounds,
        "max_pairs_per_round": requested.max_pairs_per_round,
    }
    if applied != requested_values:
        await audit_record(
            db,
            "plan_clamp",
            user_id=user.id,
            target=None,
            ip=ip,
            meta={"requested": requested_values, "applied": applied},
        )

    estimate = debate_reserve_units(
        agents=agents,
        rounds=rounds,
        max_new_per_round=body.config.max_new_agents_per_round,
        max_pairs_per_round=pairs,
    )
    # `reserve_units` rolls back on refusal, which expires the session's ORM
    # objects; capture the identity before the call so the 402 path can audit
    # it without a lazy load on an async session.
    user_id = user.id
    try:
        reservation = await billing_units.reserve_units(
            db, user_id=user_id, plan_key=user.plan_key, estimate=estimate
        )
    except billing_units.InsufficientUnits as exc:
        await audit_record(
            db,
            "units_denied",
            user_id=user_id,
            target=None,
            ip=ip,
            meta={"estimate": estimate, "period_end": exc.period_end.isoformat()},
        )
        raise payment_required(
            f"Units used up. They reset on {exc.period_end.date().isoformat()}."
        ) from exc

    config = DebateConfig(
        max_agents=agents,
        max_rounds=rounds,
        comm_radius=body.config.comm_radius,
        min_entity_overlap=body.config.min_entity_overlap,
        max_pairs_per_round=pairs,
        convergence_threshold=body.config.convergence_threshold,
        llm_concurrency=body.config.llm_concurrency,
        topology_score_threshold=body.config.topology_score_threshold,
        max_new_agents_per_round=body.config.max_new_agents_per_round,
        snapshot_top_k=body.config.snapshot_top_k,
    )

    # Durable at accept time: `enqueue` writes the queued rows before it
    # dispatches, so the 202 always follows a row that exists — and the row
    # carries the reservation, which is what the worker re-checks.
    try:
        job_id = await enqueue_or_http(
            "debate",
            {
                "user_id": str(user.id),
                "query": body.query,
                "graph_id": str(body.graph_id),
                "corpus_label": body.corpus_label,
                "config": asdict(config),
                "selected_domains": body.selected_domains,
                "simulation_depth": body.simulation_depth,
                "context": body.context,
                "correlation_id": getattr(request.state, "correlation_id", None),
                "reserved_units": reservation.amount,
                "reserved_period_start": reservation.period_start.isoformat(),
                "reserved_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception:
        # The enqueue failure is the error the caller must see; a release
        # failure is logged, never allowed to mask it.
        try:
            await billing_units.release_reservation(
                db,
                user_id=user.id,
                period_start=reservation.period_start,
                amount=reservation.amount,
            )
        except Exception as release_exc:
            logger.warning(
                "could not release reservation for user %s: %s", user.id, release_exc
            )
        else:
            await audit_record(
                db,
                "units_release",
                user_id=user.id,
                target=None,
                ip=ip,
                meta={"estimate": estimate, "reason": "enqueue_failed"},
            )
        raise

    await audit_record(
        db,
        "units_reserve",
        user_id=user.id,
        target=job_id,
        ip=ip,
        meta={
            "estimate": estimate,
            "units_used": reservation.units_used,
            "units_reserved": reservation.units_reserved,
        },
    )

    async with _DEBATE_JOBS_LOCK:
        _DEBATE_JOBS[job_id] = {
            "job_id": job_id,
            "user_id": str(user.id),
            "status": "queued",
            "query": body.query,
            "graph_id": str(body.graph_id),
            "corpus_label": body.corpus_label,
            "config": asdict(config),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "result": None,
            "error": None,
        }

    await audit_record(
        db, "run_create", user_id=user.id, target=job_id, ip=client_ip(request)
    )
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
                detail={
                    "code": "invalid_cursor",
                    "message": "The pagination cursor is not valid.",
                },
            )
    return (await run_doc.list_run_summaries(user.id))["items"]


@router.get("/debates/{run_id}")
async def get_debate_doc(run_id: str, user: User = Depends(current_user)):
    doc = await run_doc.read_run_doc(run_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Run not found")
    await require_owner(doc.get("user_id"), user)
    doc["events"] = [e for e in map(project_event, doc["events"]) if e]
    doc["result"] = project_result(doc["result"])
    return doc


@router.get("/debates/{run_id}/roster", response_model=list[AgentView])
async def get_debate_roster(run_id: str, user: User = Depends(current_user)):
    """The run's published agents, as the client may see them: AgentView only, in seat order.

    Unknown and foreign runs are the same 404, so existence is not leaked.
    """
    head = await run_doc.read_run_head(run_id)
    if head is None:
        raise HTTPException(status_code=404, detail=_FLAT_NOT_FOUND)
    await require_owner(head.get("user_id"), user)
    return await run_doc.read_roster(run_id, user.id)


#: The report prompt's size for the retry's hold. The question is the run's stored query, measured
#: (the route passes its length). The other parts are estimates from the caps the report reads: the
#: context at its byte cap, the answers, the sources and the switches. These are not code caps for
#: every part (a question is not capped in code), so the hold is an admission estimate: a report call
#: that settles above it is charged to units_used as usual (units.py), never refused for it.
REPORT_MAX_SEATS = 12  # DebateConfigRequest.max_agents, the plan cap
REPORT_MAX_ROUNDS = 20  # DebateConfigRequest.max_rounds
REPORT_SWITCH_CHARS = 200  # one switch line
REPORT_SOURCE_OVERHEAD_CHARS = 120  # the evidence tag around one source text
CHARS_PER_TOKEN = 4  # the convention UNITS_PER_CALL_TYPICAL uses


def report_prompt_chars(question_chars: int) -> int:
    """Characters of one report prompt for a question of `question_chars`: the system prompt, the context
    at its byte cap, the question, every final answer at the completion cap (max_output_tokens), every
    seat's evidence at MAX_OWN items of MAX_ITEM_CHARS, and one switch line per seat per round."""
    from src.simulation.evidence import MAX_ITEM_CHARS, MAX_OWN
    from src.simulation.verdict import REPORT_SYSTEM

    answers = REPORT_MAX_SEATS * get_llm_config().max_output_tokens * CHARS_PER_TOKEN
    sources = REPORT_MAX_SEATS * MAX_OWN * (MAX_ITEM_CHARS + REPORT_SOURCE_OVERHEAD_CHARS)
    switches = REPORT_MAX_ROUNDS * REPORT_MAX_SEATS * REPORT_SWITCH_CHARS
    return len(REPORT_SYSTEM) + CONTEXT_MAX_BYTES + max(0, question_chars) + answers + sources + switches


def report_call_units(question_chars: int) -> int:
    """Units one report call holds: its estimated prompt, and verdict_max_tokens of completion."""
    prompt_tokens = math.ceil(report_prompt_chars(question_chars) / CHARS_PER_TOKEN)
    return billing_units.units_for_tokens(prompt_tokens, get_llm_config().verdict_max_tokens)


def verdict_retry_reserve_units(question_chars: int) -> int:
    """The retry's hold: REPORT_MAX_ATTEMPTS report calls at report_call_units(question_chars), unless configured."""
    configured = get_settings().verdict_retry_reserve_units
    return configured if configured is not None else REPORT_MAX_ATTEMPTS * report_call_units(question_chars)


def verdict_retry_estimate(units_remaining: int, question_chars: int) -> int:
    """The retry's hold: the reserve capped at the user's remaining units, never below 1 (as graph jobs)."""
    return max(1, min(verdict_retry_reserve_units(question_chars), units_remaining))


def _refused(code: str) -> HTTPException:
    return HTTPException(status_code=409, detail={"code": code, "message": REFUSAL_MESSAGES[code]})


async def _release_hold(db: AsyncSession, *, user_id, reservation, ip, estimate: int, reason: str) -> None:
    """Return a hold that will not be spent. A release failure is logged, never raised over the caller's error."""
    try:
        await billing_units.release_reservation(
            db,
            user_id=user_id,
            period_start=reservation.period_start,
            amount=reservation.amount,
        )
    except Exception as release_exc:
        logger.warning("could not release reservation for user %s: %s", user_id, release_exc)
        return
    await audit_record(
        db,
        "units_release",
        user_id=user_id,
        target=None,
        ip=ip,
        meta={"estimate": estimate, "reason": reason},
    )


async def retry_verdict_report(run_id: str, owner_id: str) -> bool:
    """Rebuild a not-produced report from the run's own rows, and write it if it now passes.

    No debate runs. The board comes from the stored round events, the published records and the
    turn log; the report comes from the one writer (VerdictSynthesizer.asynthesize). A report that
    still fails its checks leaves the run not_produced, with nothing written. A rebuild that does
    not reproduce the stored board raises RetryDataError before any LLM call. MeteringError is not
    caught here. Returns True when the report was written, False when it was not produced.
    """
    from src.llm.client import LLMClient
    from src.simulation.orchestrator import result_from_verdict
    from src.simulation.report_retry import (
        RetryDataError,
        check_rebuild,
        rebuild_profiles,
        rebuild_rounds,
    )
    from src.simulation.verdict import PRODUCED, VerdictSynthesizer, board_final_stances

    run = await run_doc.read_run_doc(run_id)
    if run is None or run.get("kind") != "debate" or str(run.get("user_id")) != str(owner_id):
        raise RetryDataError("the run is not the owner's debate")
    stored = run.get("result")
    refusal = retry_refusal(stored)
    if refusal is not None:
        raise RetryDataError(f"the run is not retryable: {refusal}")
    retry_inputs = stored["retry_inputs"]
    dataset_id = str(run.get("dataset_id") or "")
    rounds = rebuild_rounds(run["events"], retry_inputs)
    profiles = rebuild_profiles(await run_doc.read_published_records(run_id), dataset_id)
    check_rebuild(rounds, profiles, stored, retry_inputs, run.get("query") or "")

    converged = bool(stored["converged"])
    verdict = await VerdictSynthesizer().asynthesize(
        rounds=rounds,
        profiles=profiles,
        llm_client=LLMClient(),
        query=run.get("query") or "",
        scenario=retry_inputs.get("context") or "",
        run_id=run_id,
        converged=converged,
    )
    if verdict.report.get("status") != PRODUCED:
        return False
    result = result_from_verdict(
        verdict,
        converged=converged,
        final_stances=board_final_stances(rounds, profiles),
        warnings=list(stored.get("warnings") or []),
        rounds_executed=len(rounds),
        intent=None,
        retry_inputs=retry_inputs,
    )
    # The one run-doc writer, as the debate path: the run's head keeps its status and corpus.
    await run_doc.write_run_doc(
        {
            "run_id": run_id,
            "user_id": run["user_id"],
            "created_at": run["created_at"],
            "status": run["status"],
            "query": run.get("query"),
            "dataset_id": run.get("dataset_id"),
            "corpus_label": run.get("corpus_label"),
            "config": run.get("config"),
            "error": run.get("error"),
            "result": stored_result(
                _job_result(result, intent=stored.get("intent"), retry_inputs=retry_inputs)
            ),
        }
    )
    return True


@router.post("/debates/{run_id}/verdict/retry", response_model=VerdictRetryResponse, status_code=202)
@limiter.limit(lambda: get_settings().rate_limit_verdict_retry)
async def retry_verdict(
    run_id: str,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    _available: None = Depends(service_available),
):
    """Re-run only the report of a run whose report was not produced. No debate runs again.

    The retry is metered like a debate: it holds the reserve (capped at the remaining units), and
    the job releases what it does not spend. Every refusal is decided before any reserve is taken,
    and a double submit enqueues nothing: the pre-check refuses it, and the database's in-flight
    index refuses a racing second insert.
    """
    head = await run_doc.read_run_head(run_id)
    if head is None or head.get("kind") != "debate":
        raise HTTPException(status_code=404, detail=_FLAT_NOT_FOUND)
    await require_owner(head.get("user_id"), user)

    refusal = retry_refusal(head.get("result"))
    if refusal is not None:
        raise _refused(refusal)
    if await run_doc.verdict_job_in_flight(run_id):
        raise _refused(REFUSAL_IN_FLIGHT)

    # `reserve_units` rolls back on refusal and commits on success, so the identity is captured first.
    user_id = user.id
    plan_key = user.plan_key
    ip = client_ip(request)
    ent = await resolve_entitlements(db, user=user)
    estimate = verdict_retry_estimate(ent.units_remaining, len(head.get("query") or ""))
    try:
        reservation = await billing_units.reserve_units(
            db, user_id=user_id, plan_key=plan_key, estimate=estimate
        )
    except billing_units.InsufficientUnits as exc:
        await audit_record(
            db,
            "units_denied",
            user_id=user_id,
            target=None,
            ip=ip,
            meta={"estimate": estimate, "period_end": exc.period_end.isoformat()},
        )
        raise payment_required(
            f"Units used up. They reset on {exc.period_end.date().isoformat()}."
        ) from exc

    created_at = datetime.now(timezone.utc).isoformat()
    try:
        job_id = await enqueue_or_http(
            "verdict",
            {
                "user_id": str(user_id),
                "run_id": run_id,
                "created_at": created_at,
                "correlation_id": getattr(request.state, "correlation_id", None),
                "reserved_units": reservation.amount,
                "reserved_period_start": reservation.period_start.isoformat(),
                "reserved_at": created_at,
            },
        )
    except run_doc.VerdictJobInFlight as exc:
        await _release_hold(
            db, user_id=user_id, reservation=reservation, ip=ip, estimate=estimate,
            reason="verdict_job_in_flight",
        )
        raise _refused(REFUSAL_IN_FLIGHT) from exc
    except Exception:
        await _release_hold(
            db, user_id=user_id, reservation=reservation, ip=ip, estimate=estimate, reason="enqueue_failed"
        )
        raise

    await audit_record(
        db,
        "units_reserve",
        user_id=user_id,
        target=job_id,
        ip=ip,
        meta={
            "estimate": estimate,
            "units_used": reservation.units_used,
            "units_reserved": reservation.units_reserved,
            "kind": "verdict",
        },
    )
    await audit_record(
        db, "verdict_retry", user_id=user_id, target=run_id, ip=ip, meta={"job_id": job_id}
    )
    return VerdictRetryResponse(job_id=job_id, run_id=run_id, status="queued")


# --- a report citation's source text (spec §0B.3 rule 1) ---------------------


class SourceUnresolved(Exception):
    """A citation that does not resolve to its stored source text. The reason is logged, never served."""


def _evidence_item(record: Mapping[str, Any], evidence_id: Any) -> Optional[Mapping[str, Any]]:
    items = record.get("evidence")
    if not isinstance(items, list):
        return None
    return next((i for i in items if isinstance(i, Mapping) and i.get("id") == evidence_id), None)


def _verified_span(item: Mapping[str, Any], chunk_text: str) -> str:
    """The stored evidence text, proven equal to the chunk's text at the stored span.

    A mismatch means the chunk changed since the run. The span is never re-aimed at other text.
    """
    span, stored = item.get("span"), item.get("text")
    if not (isinstance(span, (list, tuple)) and len(span) == 2 and all(type(x) is int for x in span)):
        raise SourceUnresolved("evidence span is not a pair of integers")
    start, end = span
    if not 0 <= start < end <= len(chunk_text):
        raise SourceUnresolved("evidence span lies outside the chunk")
    if not isinstance(stored, str) or len(stored) > MAX_ITEM_CHARS:
        raise SourceUnresolved("stored evidence text is missing or over the item bound")
    if chunk_text[start:end] != stored:
        raise SourceUnresolved("chunk text at the stored span no longer matches the evidence")
    return stored


async def resolve_source(
    n: str,
    result: Mapping[str, Any],
    *,
    read_record: Callable[[str], Awaitable[Optional[Mapping[str, Any]]]],
    read_chunk_text: Callable[[str], Awaitable[Optional[str]]],
) -> dict[str, str]:
    """Resolve citation [n] to {document, section, text}, or raise SourceUnresolved.

    The labels are the stored public sources[n], capped as the report's public labels are; the
    text is the chunk slice at the stored span, verified equal to the stored evidence text. The
    two lookups are injected, so the logic runs without a database.
    """
    refs = result.get("source_refs")
    ref = refs.get(n) if isinstance(refs, Mapping) else None
    if not isinstance(ref, Mapping):
        raise SourceUnresolved("no source ref for this number")
    sources = result.get("sources")
    label = public_source(sources.get(n)) if isinstance(sources, Mapping) else None
    if label is None:
        raise SourceUnresolved("no public label for this number")
    node_id = ref.get("node_id")
    if not isinstance(node_id, str):
        raise SourceUnresolved("source ref has no node id")
    record = await read_record(node_id)
    if record is None:
        raise SourceUnresolved("no agent record for this source")
    item = _evidence_item(record, ref.get("evidence_id"))
    if item is None:
        raise SourceUnresolved("no evidence item for this source")
    chunk_id = item.get("chunk_id")
    if not isinstance(chunk_id, str):
        raise SourceUnresolved("evidence item has no chunk id")
    chunk_text = await read_chunk_text(chunk_id)
    if chunk_text is None:
        raise SourceUnresolved("chunk is not in the run's dataset")
    return {**label, "text": _verified_span(item, chunk_text)}


# A citation number: 1 to 999, no leading zero, ASCII digits only.
_SOURCE_NUMBER = re.compile(r"[1-9][0-9]{0,2}")


@router.get("/debates/{run_id}/sources/{n}")
async def get_debate_source(run_id: str, n: str, user: User = Depends(current_user)):
    """One report citation [n], resolved to the passage it cites. Owner only.

    Every failure is the same 404. A malformed n is rejected before any lookup and never logged.
    An unknown or foreign run is caught from the run head, before any event is read. The chunk
    is read from the run's own dataset, never from the request, and the graph is opened only
    when a chunk read is due.
    """
    from src.graph.config_graph import GraphConfig
    from src.persona.graph_context import GraphContext

    if not _SOURCE_NUMBER.fullmatch(n):
        raise HTTPException(status_code=404, detail=_FLAT_NOT_FOUND)
    head = await run_doc.read_run_head(run_id)
    if head is None:
        logger.warning("source %s: run %s is unknown", n, run_id)
        raise HTTPException(status_code=404, detail=_FLAT_NOT_FOUND)
    try:
        await require_owner(head.get("user_id"), user)
    except HTTPException:
        logger.warning("source %s: run %s is not the caller's", n, run_id)
        raise HTTPException(status_code=404, detail=_FLAT_NOT_FOUND)
    result = head.get("result")
    dataset_id = await run_doc.read_run_dataset(run_id) if isinstance(result, Mapping) else None
    if not dataset_id or not isinstance(result, Mapping):
        logger.warning("source %s: run %s has no report or no corpus", n, run_id)
        raise HTTPException(status_code=404, detail=_FLAT_NOT_FOUND)

    async def read_chunk_text(chunk_id: str) -> Optional[str]:
        async with GraphContext(GraphConfig()) as ctx:
            return await ctx.fetch_chunk_text(chunk_id, str(dataset_id))

    try:
        return await resolve_source(
            n,
            result,
            read_record=lambda node_id: run_doc.read_agent_record(run_id, node_id),
            read_chunk_text=read_chunk_text,
        )
    except SourceUnresolved as exc:
        logger.warning("source %s of run %s not resolved: %s", n, run_id, exc)
        raise HTTPException(status_code=404, detail=_FLAT_NOT_FOUND)

# --- a run's corpus (the replay path's seed) ---------------------------------

# The four reasons a run's graph can be missing, told apart by their `code`:
# "run_not_found" (no such run), "not_yours" (someone else's — still 404, never
# 403, so existence is never leaked), "no_corpus" (the run never named one), and
# "corpus_gone" (it named one and the graph no longer holds it). The last two
# are separate on purpose: the frontend says "no sources" for one and "sources
# unavailable" for the other.
_FLAT_NOT_FOUND = "Not found."  # identical for unknown and foreign


def _missing_run(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": code, "message": message})


def _snapshot_field(snapshot, name: str, default):
    """One field off the snapshot read.

    The reader hands back a `GraphDelta`; a mapping is accepted too, so the
    route's payload contract is the field names, not the reader's class.
    """
    value = (
        snapshot.get(name)
        if isinstance(snapshot, dict)
        else getattr(snapshot, name, None)
    )
    return default if value is None else value


@router.get("/debates/{run_id}/graph")
async def get_debate_graph(run_id: str, user: User = Depends(current_user)):
    """The run's stored map — its corpus id, every node and edge, the vocabulary.

    Reopening a finished run reads this plus the persisted events and rebuilds
    the identical graph. Read-only truth: the existing dataset-scoped snapshot
    read is the only graph access, so this invents nothing.
    """
    doc = await run_doc.read_run_doc(run_id)
    if doc is None or doc.get("kind") != "debate":
        raise _missing_run("run_not_found", _FLAT_NOT_FOUND)
    try:
        await require_owner(doc.get("user_id"), user)
    except HTTPException:
        raise _missing_run("not_yours", _FLAT_NOT_FOUND)

    dataset_id = doc.get("dataset_id")
    if not dataset_id:
        raise _missing_run("no_corpus", "This run names no corpus.")

    try:
        snapshot = await read_graph_snapshot(str(dataset_id))
    except Exception as exc:
        # A corpus that cannot be read is a calm typed 404, not a 500: the
        # frontend's answer is the same as for a corpus that was emptied, and a
        # raise here would report a server fault for a run whose graph simply is
        # not there. Logged, never swallowed.
        logger.warning("graph read failed for dataset %s: %s", dataset_id, exc)
        raise _missing_run("corpus_gone", "This run's corpus is gone.")

    nodes = _snapshot_field(snapshot, "nodes", [])
    if not nodes:
        raise _missing_run("corpus_gone", "This run's corpus is gone.")
    return {
        "dataset_id": str(dataset_id),
        "nodes": nodes,
        "edges": _snapshot_field(snapshot, "edges", []),
        "labels": _snapshot_field(snapshot, "labels", None)
        or _snapshot_field(snapshot, "new_labels", []),
        "chunk_count": _snapshot_field(snapshot, "chunk_count", 0),
    }


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
        result=project_result(head["result"]),
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
