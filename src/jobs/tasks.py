"""Job functions and the shared lifecycle (plan §5).

``execute`` is the one lifecycle wrapper, used by both dispatch modes: it puts
the request's correlation id into the logging context, transitions the rows
``queued → running``, runs the kind's async core under its per-kind timeout, and
writes the terminal state — ``complete``/``completed`` on success, ``failed``
with the error text on a raise, ``cancelled`` when the cancel flag was set.

The ``run_debate``/``ontology``/… functions are the RQ worker targets: RQ calls
sync functions, so each one is ``asyncio.run(execute(...))``. ``inline`` mode
(the dev fallback on Windows) calls ``execute`` on the API process's own loop
directly — RQ workers are fork-based and cannot run here, and the process's DB
engine is bound to its loop. Only the trampoline differs; the lifecycle and row
writes are the same code.
"""

import asyncio
import logging
from typing import Any

from src.jobs.queue import (
    cancel_check,
    is_cancelled,
    timeout_for,
)
from src.logging.setup_logging import reset_correlation_id, set_correlation_id

logger = logging.getLogger(__name__)


class JobCancelled(RuntimeError):
    """The owner cancelled the job; a terminal ``cancelled``, not a failure."""


#: Terminal status on success, per kind (the row convention each body already
#: writes: runs are ``complete``, graph jobs ``completed``).
_SUCCESS_STATUS = {
    "debate": "complete",
    "ontology": "completed",
    "build_graph": "completed",
    "normalize_graph": "completed",
}


async def _debate_core(job_id: str, payload: dict[str, Any]) -> None:
    from src.api import debate_api
    from src.simulation.debate_config import DebateConfig
    from src.simulation.orchestrator import DebateCancelled

    try:
        await debate_api._run_debate_async(
            job_id=job_id,
            query=payload["query"],
            graph_id=payload.get("graph_id") or "simulation_runtime",
            config=DebateConfig(**payload["config"]),
            selected_domains=payload.get("selected_domains"),
            simulation_depth=payload.get("simulation_depth") or "standard",
            context=payload.get("context"),
            cancel_check=cancel_check(job_id),
        )
    except DebateCancelled as exc:
        raise JobCancelled(str(exc)) from exc


def _documents(payload: dict[str, Any]):
    from src.graph.models_graph import GlobalInputDocument

    return [
        GlobalInputDocument.model_validate(doc)
        for doc in payload.get("documents") or []
    ]


async def _ontology_core(job_id: str, payload: dict[str, Any]) -> None:
    from src.api import api_server

    await api_server.run_graph_job(
        job_id, "ontology", payload["dataset_id"], _documents(payload)
    )


async def _build_graph_core(job_id: str, payload: dict[str, Any]) -> None:
    from src.api import api_server

    await api_server.run_graph_job(
        job_id,
        "build_graph",
        payload["dataset_id"],
        _documents(payload),
        ontology_job_id=payload.get("ontology_job_id"),
    )


async def _normalize_graph_core(job_id: str, payload: dict[str, Any]) -> None:
    from src.api import api_server

    await api_server.run_normalize_job(job_id, payload["dataset_id"])


#: kind → async core. The tests swap a core out to drive the lifecycle without
#: standing up Neo4j/LLM.
CORES = {
    "debate": _debate_core,
    "ontology": _ontology_core,
    "build_graph": _build_graph_core,
    "normalize_graph": _normalize_graph_core,
}


async def _set_status(
    job_id: str, status: str, error: str | None = None, only_if_active: bool = False
) -> None:
    from src.api import run_doc

    try:
        await run_doc.set_job_status(
            job_id, status, error=error, only_if_active=only_if_active
        )
    except Exception as exc:
        # Never swallow, but never let a bookkeeping failure mask the job's own
        # error: the raise below is what the caller (RQ) must see.
        logger.error("could not write %s for job %s: %s", status, job_id, exc)


async def execute(kind: str, job_id: str, payload: dict[str, Any]) -> None:
    """Run one job end to end, leaving its rows terminal on every exit path."""
    token = set_correlation_id(payload.get("correlation_id"))
    logger.info("job %s (%s) starting", job_id, kind)
    try:
        if is_cancelled(job_id):
            logger.info("job %s (%s) cancelled before it started", job_id, kind)
            await _set_status(job_id, "cancelled")
            return

        await _set_status(job_id, "running")
        timeout = timeout_for(kind)
        try:
            await asyncio.wait_for(CORES[kind](job_id, payload), timeout=timeout)
        except (asyncio.TimeoutError, TimeoutError):
            message = f"job exceeded its {timeout}s timeout"
            logger.error("job %s (%s): %s", job_id, kind, message)
            await _set_status(job_id, "failed", error=message)
            raise
        except JobCancelled as exc:
            logger.info("job %s (%s) cancelled: %s", job_id, kind, exc)
            await _set_status(job_id, "cancelled")
            return
        except Exception as exc:
            logger.error("job %s (%s) failed: %s", job_id, kind, exc, exc_info=exc)
            await _set_status(job_id, "failed", error=str(exc))
            raise
        # The body owns the result and writes the richer terminal row itself; a
        # body that failed before any write (or a bare test core) still lands
        # terminal here. `only_if_active` keeps a body's own `failed` standing.
        await _set_status(job_id, _SUCCESS_STATUS[kind], only_if_active=True)
        logger.info("job %s (%s) finished", job_id, kind)
    finally:
        reset_correlation_id(token)


def run_debate(job_id: str, payload: dict[str, Any]) -> None:
    asyncio.run(execute("debate", job_id, payload))


def ontology(job_id: str, payload: dict[str, Any]) -> None:
    asyncio.run(execute("ontology", job_id, payload))


def build_graph(job_id: str, payload: dict[str, Any]) -> None:
    asyncio.run(execute("build_graph", job_id, payload))


def normalize_graph(job_id: str, payload: dict[str, Any]) -> None:
    asyncio.run(execute("normalize_graph", job_id, payload))


#: The RQ targets, by kind.
TASKS = {
    "debate": run_debate,
    "ontology": ontology,
    "build_graph": build_graph,
    "normalize_graph": normalize_graph,
}
