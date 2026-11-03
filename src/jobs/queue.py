"""Queue dispatch for background jobs (plan §5).

Rows are the only job truth (Task 5): ``enqueue`` writes the queued ``jobs``/
``runs`` row, then hands the job to a dispatcher. The dispatcher has two modes
behind one interface (R16), settings-driven by ``QUEUE_MODE``:

* ``rq`` — the job id goes on an RQ queue; ``src/jobs/worker.py`` is the Linux
  worker entrypoint (containerized in Task 8).
* ``inline`` — the same ``src/jobs/tasks.py`` function runs in-process on the
  running loop. Dev-only fallback: RQ workers are fork-based and cannot run on
  Windows, so this is what makes the golden path runnable on this machine.

The rows/lifecycle code is identical in both modes; only the dispatch call
differs.
"""

import asyncio
import logging
import uuid
from typing import Any, Optional

import redis
from rq import Queue, Retry

from src.api import run_doc
from src.config.settings import get_settings

logger = logging.getLogger(__name__)

#: One queue for every kind — the worker registers one queue and the registry
#: (``tasks.TASKS``) resolves the function per job.
QUEUE_NAME = "societas"

#: Redis key holding a job's cancel flag; TTL-bounded (see ``cancel_ttl_seconds``)
#: so an abandoned flag cannot outlive the job it was meant for.
CANCEL_KEY_PREFIX = "job_cancel:"

#: How long a client should wait before retrying a capped enqueue. The slot
#: frees when any in-flight job finishes — below the shortest job timeout.
RETRY_AFTER_SECONDS = 30

_redis: Optional[redis.Redis] = None
_queue: Optional[Queue] = None

#: In-flight inline jobs (task → job id), so a test (or shutdown) can await
#: them and a failure can name the job it never retried.
_INLINE_TASKS: dict[asyncio.Task, str] = {}


class JobLimitExceeded(RuntimeError):
    """The caller already has the maximum number of jobs in flight."""

    def __init__(self, limit: int):
        self.limit = limit
        super().__init__(
            f"At most {limit} jobs may be in flight at once — wait for one to finish."
        )


class JobValidationError(ValueError):
    """The payload cannot name a runnable job. Rejected before enqueue, so an
    unretryable mistake never becomes an RQ retry (the work is not idempotent)."""


def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(get_settings().redis_url)
    return _redis


def get_queue() -> Queue:
    global _queue
    if _queue is None:
        _queue = Queue(QUEUE_NAME, connection=get_redis())
    return _queue


def timeout_for(kind: str) -> int:
    """Per-kind wall-clock ceiling, enforced by the worker/mode wrapper."""
    settings = get_settings()
    if kind == "debate":
        return settings.job_timeout_debate_seconds
    return settings.job_timeout_graph_seconds


def cancel_ttl_seconds() -> int:
    """Longer than any job's timeout, so a cancel flag outlives the job."""
    settings = get_settings()
    return (
        max(settings.job_timeout_debate_seconds, settings.job_timeout_graph_seconds)
        + 60
    )


def _cancel_key(job_id: str) -> str:
    return f"{CANCEL_KEY_PREFIX}{job_id}"


def set_cancel(job_id: str) -> None:
    get_redis().setex(_cancel_key(job_id), cancel_ttl_seconds(), "1")


def is_cancelled(job_id: str) -> bool:
    return bool(get_redis().exists(_cancel_key(job_id)))


def clear_cancel(job_id: str) -> None:
    get_redis().delete(_cancel_key(job_id))


def cancel_check(job_id: str):
    """The ``cancel_check`` the job body polls between rounds/batches."""
    return lambda: is_cancelled(job_id)


def _spawn_inline(coro, job_id: str) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _INLINE_TASKS[task] = job_id
    task.add_done_callback(_note_inline_result)
    return task


def _note_inline_result(task: asyncio.Task) -> None:
    job_id = _INLINE_TASKS.pop(task, None)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        # `execute` already wrote the failure to the rows; this is the log the
        # bare task would otherwise lose as "exception was never retrieved".
        # Inline mode never retries (R16 dev fallback), so say so — a failure
        # here is final, unlike the same failure on the RQ path.
        logger.warning(
            "inline job %s failed and will not be retried: %s",
            job_id,
            exc,
            exc_info=exc,
        )


async def drain_inline() -> None:
    """Await every in-flight inline job — tests and graceful shutdown."""
    while _INLINE_TASKS:
        await asyncio.gather(*list(_INLINE_TASKS), return_exceptions=True)


def cancel_inline() -> int:
    """Cancel every in-flight inline job (graceful shutdown). Their rows stay
    ``running``; the next boot's interrupted sweep reconciles them (§7.10)."""
    tasks = list(_INLINE_TASKS)
    for task in tasks:
        task.cancel()
    return len(tasks)


async def graceful_shutdown(seconds: int) -> None:
    """Bounded drain of in-flight work at API shutdown (plan §9).

    The API process never blocks past ``seconds``. In ``rq`` mode the worker owns
    execution and RQ salvages its own in-flight job on SIGTERM (finish or
    requeue) — the API process holds nothing to drain. In ``inline`` mode the
    process runs the jobs itself: give them up to ``seconds`` to finish, then
    cancel what remains (their rows stay ``running`` for the boot sweep).
    """
    if get_settings().queue_mode == "rq":
        logger.info("shutdown: rq mode — the worker salvages its in-flight job")
        return
    try:
        await asyncio.wait_for(drain_inline(), timeout=seconds)
        logger.info("shutdown: inline jobs drained")
    except (asyncio.TimeoutError, TimeoutError):
        cancelled = cancel_inline()
        logger.warning(
            "shutdown: inline drain exceeded %ss — cancelled %d in-flight job(s)",
            seconds,
            cancelled,
        )


def _tasks():
    """The task registry (lazy: ``tasks`` imports this module back)."""
    from src.jobs import tasks

    return tasks


async def _write_queued_rows(kind: str, job_id: str, payload: dict[str, Any]) -> None:
    user_id = payload["user_id"]
    created_at = payload.get("created_at")
    if kind == "debate":
        await run_doc.write_run_doc(
            {
                "run_id": job_id,
                "user_id": user_id,
                "created_at": created_at,
                "status": "queued",
                "query": payload.get("query"),
                "dataset_id": payload.get("graph_id"),
                "corpus_label": payload.get("corpus_label"),
                "config": payload.get("config"),
                "reserved_units": payload.get("reserved_units") or 0,
                "reserved_period_start": payload.get("reserved_period_start"),
                "reserved_at": payload.get("reserved_at"),
                "result": None,
                "error": None,
            }
        )
        return
    await run_doc.write_job_doc(
        {
            "job_id": job_id,
            "user_id": user_id,
            "created_at": created_at,
            "mode": kind,
            "status": "queued",
            "progress": 0.0,
            "stage": "queued",
            "error": None,
            "result": None,
        }
    )


def _dispatch(kind: str, job_id: str, payload: dict[str, Any]) -> None:
    tasks = _tasks()
    if get_settings().queue_mode == "rq":
        get_queue().enqueue(
            tasks.TASKS[kind],
            job_id,
            payload,
            job_timeout=timeout_for(kind),
            retry=Retry(
                max=get_settings().job_retry_max,
                interval=list(get_settings().job_retry_intervals),
            ),
        )
        return
    _spawn_inline(tasks.execute(kind, job_id, payload), job_id)


async def enqueue(kind: str, payload: dict[str, Any]) -> str:
    """Write the queued rows for a new job and dispatch it. Returns its id.

    Raises :class:`JobValidationError` for a payload that cannot name a runnable
    job and :class:`JobLimitExceeded` when the owner is at the concurrency cap —
    both before anything is written or queued.
    """
    tasks = _tasks()
    if not payload.get("user_id") or kind not in tasks.TASKS:
        raise JobValidationError(f"{kind!r} is not a job kind this build can run.")
    if (
        await run_doc.count_active_jobs(payload["user_id"])
        >= get_settings().max_jobs_per_user
    ):
        raise JobLimitExceeded(get_settings().max_jobs_per_user)
    job_id = str(uuid.uuid4())
    await _write_queued_rows(kind, job_id, payload)
    try:
        _dispatch(kind, job_id, payload)
    except Exception as exc:
        # The queued row is already written, so a dispatch failure (Redis down,
        # RQ error) would otherwise orphan it `queued` forever — unswept (only
        # `running` rows are reconciled) and counted by the cap, permanently
        # 429-ing the owner for a job that never ran. Mark it terminal first.
        logger.error(
            "could not dispatch %s job %s: %s", kind, job_id, exc, exc_info=exc
        )
        await run_doc.set_job_status(job_id, "failed", error=str(exc))
        raise
    logger.info("enqueued %s job %s", kind, job_id)
    return job_id
