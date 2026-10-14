"""Postgres-backed run/job store (§4 persistence, §13 migration).

Rows are the truth. The in-process dicts (`api_server.RUNS`,
`debate_api._DEBATE_JOBS`) are live-process working state, never an answer
source: every read below goes to the database.

The doc shapes are unchanged — the routes and the frontend speak them:

    job doc: job_id, user_id, mode, status, progress, stage, error, result
    run doc: run_id, user_id, created_at, query, dataset_id, config, status,
             events[], result

Row mapping (no column was added for this):

* ``jobs`` — one row per job, both kinds. ``kind`` carries the job's ``mode``
  (``debate`` for runs); ``error``/timestamps/ownership live here.
* ``runs`` — one head row per job (``jobs.run_id == jobs.id``). For a debate it
  is the run itself: ``verdict`` = the result doc, ``confidence`` its score.
  For a graph job the schema has no stage/progress columns, so ``verdict``
  carries ``{"stage", "progress", "result"}``.
* ``run_events`` — the per-run ordered log. For debates, ``seq`` 0 is the
  ``run_meta`` row (``dataset_id``/``config`` have no columns either) and each
  streamed event follows at ``seq = buffer index + 1``.

The legacy JSON mirrors under ``src/api/runtime/`` are no longer written or
read — they are read-only history for ``scripts/migrate_runtime_json.py``.
"""
import base64
import datetime
import logging
import uuid
from typing import Any, Optional

from sqlalchemy import func, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.db.engine import get_session_factory
from src.db.models import Job, Run, RunEvent

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {"complete", "completed", "failed", "cancelled"}

RUN_META = "run_meta"


class InvalidCursor(ValueError):
    """A cursor that is not one of ours (malformed, truncated, or forged)."""


def _as_uuid(value: uuid.UUID | str | None) -> Optional[uuid.UUID]:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _parse_dt(value: Any) -> Optional[datetime.datetime]:
    if isinstance(value, datetime.datetime):
        return value if value.tzinfo else value.replace(tzinfo=datetime.timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=datetime.timezone.utc)
    return None


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _encode_cursor(created_at: datetime.datetime, run_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{run_id}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime.datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        created_raw, _, id_raw = raw.rpartition("|")
        created_at = datetime.datetime.fromisoformat(created_raw)
        run_id = uuid.UUID(id_raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidCursor(f"unreadable cursor: {exc}") from exc
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=datetime.timezone.utc)
    return created_at, run_id


def _job_values(doc: dict[str, Any], job_id: uuid.UUID, user_id: uuid.UUID, kind: str) -> dict[str, Any]:
    status = doc.get("status") or "queued"
    return {
        "id": job_id,
        "user_id": user_id,
        "run_id": job_id,
        "kind": kind,
        "status": status,
        "error": doc.get("error"),
        "queued_at": _parse_dt(doc.get("created_at")) or _now(),
        "started_at": _now() if status == "running" else None,
        "finished_at": _now() if status in TERMINAL_STATUSES else None,
    }


def _upsert_job(session, values: dict[str, Any]):
    statement = pg_insert(Job).values(**values)
    return session.execute(
        statement.on_conflict_do_update(
            index_elements=[Job.id],
            set_={
                "status": statement.excluded.status,
                "error": statement.excluded.error,
                # First transition wins; a later write never un-stamps a timestamp.
                "started_at": func.coalesce(Job.started_at, statement.excluded.started_at),
                "finished_at": func.coalesce(Job.finished_at, statement.excluded.finished_at),
            },
        )
    )


def _upsert_run(
    session,
    *,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    query: str,
    status: str,
    verdict: Optional[dict],
    confidence: Optional[float],
    created_at: datetime.datetime,
    finished_at: Optional[datetime.datetime],
):
    statement = pg_insert(Run).values(
        id=run_id,
        user_id=user_id,
        query=query,
        status=status,
        verdict=verdict,
        confidence=confidence,
        created_at=created_at,
        finished_at=finished_at,
    )
    return session.execute(
        statement.on_conflict_do_update(
            index_elements=[Run.id],
            set_={
                "status": statement.excluded.status,
                "verdict": statement.excluded.verdict,
                "confidence": statement.excluded.confidence,
                "finished_at": func.coalesce(Run.finished_at, statement.excluded.finished_at),
            },
        )
    )


# --- graph jobs (ontology / build_graph / normalize_graph) -------------------


async def write_job_doc(doc: dict[str, Any]) -> None:
    """Upsert a graph job's rows from its doc shape (idempotent by job_id)."""
    job_id = _as_uuid(doc.get("job_id"))
    user_id = _as_uuid(doc.get("user_id"))
    if job_id is None or user_id is None:
        raise ValueError(f"job doc {doc.get('job_id')!r} has no uuid job_id/user_id")
    result = doc.get("result")
    state = {
        "stage": doc.get("stage"),
        "progress": doc.get("progress"),
        "result": result,
    }
    async with get_session_factory()() as session:
        # runs first: jobs.run_id carries an FK to it.
        await _upsert_run(
            session,
            run_id=job_id,
            user_id=user_id,
            query=str((result or {}).get("dataset_id") or ""),
            status=doc.get("status") or "queued",
            verdict=state,
            confidence=None,
            created_at=_parse_dt(doc.get("created_at")) or _now(),
            finished_at=_now() if (doc.get("status") in TERMINAL_STATUSES) else None,
        )
        await _upsert_job(session, _job_values(doc, job_id, user_id, str(doc.get("mode") or "job")))
        await session.commit()


async def read_job_doc(job_id: str) -> Optional[dict[str, Any]]:
    """The job doc for an id, assembled from rows — None when unknown."""
    key = _as_uuid(job_id)
    if key is None:
        return None
    async with get_session_factory()() as session:
        job = await session.get(Job, key)
        if job is None:
            return None
        run = await session.get(Run, key)
    state = (run.verdict if run is not None else None) or {}
    return {
        "job_id": str(job.id),
        "user_id": str(job.user_id),
        "mode": job.kind,
        "status": job.status,
        "stage": state.get("stage") or job.status,
        "progress": state.get("progress") if state.get("progress") is not None else 0.0,
        "error": job.error,
        "result": state.get("result"),
    }


# --- debate runs -------------------------------------------------------------


async def write_run_doc(doc: dict[str, Any]) -> None:
    """Upsert a run's head rows (jobs + runs) and its ``run_meta`` event."""
    run_id = _as_uuid(doc.get("run_id"))
    user_id = _as_uuid(doc.get("user_id"))
    if run_id is None or user_id is None:
        raise ValueError(f"run doc {doc.get('run_id')!r} has no uuid run_id/user_id")
    status = doc.get("status") or "queued"
    result = doc.get("result")
    confidence = result.get("confidence_score") if isinstance(result, dict) else None
    created_at = _parse_dt(doc.get("created_at")) or _now()
    finished_at = _now() if status in TERMINAL_STATUSES else None

    async with get_session_factory()() as session:
        # runs first: jobs.run_id carries an FK to it.
        await _upsert_run(
            session,
            run_id=run_id,
            user_id=user_id,
            query=str(doc.get("query") or ""),
            status=status,
            verdict=result if isinstance(result, dict) else None,
            confidence=confidence,
            created_at=created_at,
            finished_at=finished_at,
        )
        await _upsert_job(session, _job_values(doc, run_id, user_id, "debate"))
        await session.execute(
            pg_insert(RunEvent)
            .values(
                id=uuid.uuid4(),
                run_id=run_id,
                seq=0,
                type=RUN_META,
                payload={"dataset_id": doc.get("dataset_id"), "config": doc.get("config")},
            )
            .on_conflict_do_nothing(index_elements=["run_id", "seq"])
        )
        await session.commit()


async def append_run_event(run_id: str, seq: int, event: dict[str, Any]) -> None:
    """Append one streamed event to the run's log (seq is per-run monotonic)."""
    key = _as_uuid(run_id)
    if key is None:
        raise ValueError(f"run event for non-uuid run id {run_id!r}")
    async with get_session_factory()() as session:
        await session.execute(
            pg_insert(RunEvent)
            .values(
                id=uuid.uuid4(),
                run_id=key,
                seq=seq,
                type=str(event.get("type") or "event"),
                payload=event,
            )
            .on_conflict_do_nothing(index_elements=["run_id", "seq"])
        )
        await session.commit()


async def read_run_head(run_id: str) -> Optional[dict[str, Any]]:
    """A run's head state (no events) — the status-poll read."""
    key = _as_uuid(run_id)
    if key is None:
        return None
    async with get_session_factory()() as session:
        run = await session.get(Run, key)
        if run is None:
            return None
        job = await session.get(Job, key)
    return {
        "run_id": str(run.id),
        "user_id": str(run.user_id),
        "kind": job.kind if job is not None else None,
        "created_at": run.created_at.isoformat(),
        "query": run.query,
        "status": run.status,
        "result": run.verdict,
        "error": job.error if job is not None else None,
    }


async def read_run_doc(run_id: str) -> Optional[dict[str, Any]]:
    """The full run doc (head + meta + events) — None when unknown."""
    head = await read_run_head(run_id)
    if head is None:
        return None
    key = _as_uuid(run_id)
    async with get_session_factory()() as session:
        rows = (
            await session.execute(
                select(RunEvent).where(RunEvent.run_id == key).order_by(RunEvent.seq)
            )
        ).scalars().all()
    meta = next((row.payload for row in rows if row.type == RUN_META), None) or {}
    head.update(
        {
            "dataset_id": meta.get("dataset_id"),
            "config": meta.get("config"),
            "events": [row.payload for row in rows if row.type != RUN_META],
        }
    )
    return head


def _summarize(run: Run, error: Optional[str], meta: dict, rounds_from_events: int) -> dict[str, Any]:
    result = run.verdict or {}
    clusters = result.get("cluster_details") or {}
    verdict_stance = None
    if clusters:
        dominant = max(clusters.values(), key=lambda cluster: cluster.get("total_weight", 0.0))
        verdict_stance = dominant.get("stance")
    status = run.status
    if status == "failed" and error == "interrupted":
        # The boot sweep's mark — the honest "server restarted mid-run" (§7.10).
        status = "interrupted"
    return {
        "run_id": str(run.id),
        "created_at": run.created_at.isoformat(),
        "query": run.query,
        "dataset_id": meta.get("dataset_id"),
        "status": status,
        "rounds_executed": result.get("rounds_executed", rounds_from_events),
        "converged": result.get("converged"),
        "verdict_stance": verdict_stance,
    }


async def list_run_summaries(
    user_id: uuid.UUID | str,
    limit: Optional[int] = None,
    cursor: Optional[str] = None,
) -> dict[str, Any]:
    """Owned debate runs, newest-first — keyset over ``(created_at, id)`` DESC.

    ``limit=None`` (the legacy alias) returns every owned run in one page.
    ``cursor`` is the opaque ``next_cursor`` of the previous page; a cursor
    that is not ours raises :class:`InvalidCursor` (the route maps it to 400).
    """
    owner = _as_uuid(user_id)
    key = _decode_cursor(cursor) if cursor else None
    async with get_session_factory()() as session:
        statement = (
            select(Run, Job.error)
            .join(Job, Job.id == Run.id)
            .where(Run.user_id == owner, Job.kind == "debate")
            .order_by(Run.created_at.desc(), Run.id.desc())
        )
        if key is not None:
            statement = statement.where(tuple_(Run.created_at, Run.id) < key)
        if limit is not None:
            statement = statement.limit(limit + 1)  # one extra tells us there is a next page
        rows = (await session.execute(statement)).all()
        has_more = limit is not None and len(rows) > limit
        page = rows[:limit] if limit is not None else rows

        ids = [run.id for run, _ in page]
        metas: dict[uuid.UUID, dict] = {}
        rounds: dict[uuid.UUID, int] = {}
        if ids:
            events = (
                await session.execute(
                    select(RunEvent.run_id, RunEvent.type, RunEvent.payload).where(
                        RunEvent.run_id.in_(ids), RunEvent.type.in_([RUN_META, "stage"])
                    )
                )
            ).all()
            for run_id, event_type, payload in events:
                if event_type == RUN_META:
                    metas[run_id] = payload or {}
                elif (payload or {}).get("stage") == "round":
                    rounds[run_id] = rounds.get(run_id, 0) + 1

    items = [
        _summarize(run, error, metas.get(run.id) or {}, rounds.get(run.id, 0))
        for run, error in page
    ]
    next_cursor = _encode_cursor(page[-1][0].created_at, page[-1][0].id) if has_more else None
    return {"items": items, "next_cursor": next_cursor}


# --- job lifecycle (the queue's running/terminal transitions) ----------------

async def set_job_status(
    job_id: str,
    status: str,
    error: Optional[str] = None,
    only_if_active: bool = False,
) -> bool:
    """Move a job's rows to ``status`` without touching the result payload.

    The queue lifecycle owns the transitions (``running`` on start, the terminal
    state on success/failure/cancel); the job body owns the result — so this
    writes ``jobs.status``/``error``/timestamps plus the run's status only, never
    ``runs.verdict``. Returns False for an unknown or non-uuid id.

    ``only_if_active`` skips a row that already reached a terminal state: the
    first terminal writer wins, so the lifecycle's success marker cannot
    overwrite a body that already recorded a failure.
    """
    key = _as_uuid(job_id)
    if key is None:
        return False
    now = _now()
    terminal = status in TERMINAL_STATUSES
    match = update(Job).where(Job.id == key)
    if only_if_active:
        match = match.where(Job.status.notin_(TERMINAL_STATUSES))
    async with get_session_factory()() as session:
        applied = await session.execute(
            match.values(
                status=status,
                error=error,
                started_at=func.coalesce(Job.started_at, now if status == "running" else None),
                finished_at=func.coalesce(Job.finished_at, now if terminal else None),
            )
        )
        if not applied.rowcount and only_if_active:
            # The row is already terminal: leave the run's status alone too.
            await session.commit()
            return False
        run = (
            update(Run).where(Run.id == key).values(status=status)
            if not terminal
            else update(Run)
            .where(Run.id == key)
            .values(status=status, finished_at=func.coalesce(Run.finished_at, now))
        )
        await session.execute(run)
        await session.commit()
    return bool(applied.rowcount)


async def count_active_jobs(user_id: uuid.UUID | str) -> int:
    """Non-terminal jobs owned by a user, across every kind — the concurrency cap."""
    owner = _as_uuid(user_id)
    if owner is None:
        return 0
    async with get_session_factory()() as session:
        return (
            await session.execute(
                select(func.count())
                .select_from(Job)
                .where(Job.user_id == owner, Job.status.notin_(TERMINAL_STATUSES))
            )
        ).scalar_one()


# --- boot reconciliation -----------------------------------------------------


async def sweep_interrupted() -> int:
    """Mark rows still ``running`` as failed/'interrupted'.

    Single-process reality: at boot nothing is running, so a ``running`` row is
    a run this process can never resume (§7.10). The heartbeat variant waits
    for multi-replica (Task 8+). Returns the number of jobs swept.
    """
    now = _now()
    async with get_session_factory()() as session:
        jobs = await session.execute(
            update(Job)
            .where(Job.status == "running")
            .values(status="failed", error="interrupted", finished_at=now)
        )
        await session.execute(
            update(Run).where(Run.status == "running").values(status="failed", finished_at=now)
        )
        await session.commit()
    return jobs.rowcount or 0
