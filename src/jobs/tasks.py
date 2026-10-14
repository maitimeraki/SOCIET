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
import base64
import json
import logging
import uuid
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
    "extract_upload": "completed",
    "account_delete": "completed",
    "account_export": "completed",
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


def _read_object(object_key: str) -> bytes:
    from src.ingest.storage import get_upload

    with get_upload(object_key) as body:
        return body.read()


async def _extract_file_upload(
    user_id: str, upload_id: str, filename: str, timeout: int, max_output_bytes: int
) -> None:
    """Read one stored object, re-sniff it, extract it in the bounded child."""
    from src.db.engine import get_session_factory
    from src.ingest import repository
    from src.ingest.bounded import run_extraction
    from src.ingest.extract import ExtractionError, validate_upload

    async with get_session_factory()() as session:
        row = await repository.get_upload_row(session, upload_id)
        if row is None or str(row.user_id) != str(user_id):
            raise ExtractionError(f"upload {upload_id} is not on the job's owner")
        object_key = row.object_key

    data = await asyncio.to_thread(_read_object, object_key)
    # Defense in depth: the route already sniffed this, but the bytes have left
    # the process (bucket round-trip) since then.
    validate_upload(filename, data)
    result = await asyncio.to_thread(
        run_extraction,
        {
            "kind": "file",
            "filename": filename,
            "data": base64.b64encode(data).decode("ascii"),
        },
        timeout=timeout,
        max_output_bytes=max_output_bytes,
    )
    async with get_session_factory()() as session:
        row = await repository.get_upload_row(session, upload_id)
        if row is not None:
            row.extracted_text = json.dumps(result["document"], ensure_ascii=False)
            await session.commit()


async def _extract_url_upload(
    user_id: str, url: str, timeout: int, max_output_bytes: int
) -> str:
    """Fetch + extract one URL in the bounded child; record it as an upload row.

    A URL has no object to store, so ``object_key`` is the source URL itself —
    the row is only a carrier for the extracted payload the documents endpoint
    serves. Returns the new upload id.
    """
    from src.db.engine import get_session_factory
    from src.ingest import repository
    from src.ingest.bounded import run_extraction

    result = await asyncio.to_thread(
        run_extraction,
        {"kind": "url", "url": url},
        timeout=timeout,
        max_output_bytes=max_output_bytes,
    )
    meta = result["meta"]
    upload_id = uuid.uuid4()
    async with get_session_factory()() as session:
        repository.insert_upload(
            session,
            upload_id=upload_id,
            user_id=uuid.UUID(str(user_id)),
            object_key=meta["source_url"],
            size=meta["bytes"],
            mime="text/html",
            sha256=meta["sha256"],
            extracted_text=json.dumps(result["document"], ensure_ascii=False),
        )
        await session.commit()
    return str(upload_id)


async def _extract_upload_core(job_id: str, payload: dict[str, Any]) -> None:
    """The extraction job body: file batch or one URL, output into the rows."""
    from src.api import run_doc
    from src.config.settings import get_settings

    settings = get_settings()
    timeout = settings.extract_timeout_seconds
    max_output_bytes = settings.extract_max_output_bytes
    user_id = payload["user_id"]

    if payload.get("kind") == "url":
        upload_ids = [
            await _extract_url_upload(
                user_id, payload["url"], timeout, max_output_bytes
            )
        ]
    else:
        filenames = payload.get("filenames") or {}
        upload_ids = list(payload["upload_ids"])
        for upload_id in upload_ids:
            await _extract_file_upload(
                user_id,
                upload_id,
                filenames.get(upload_id) or upload_id,
                timeout,
                max_output_bytes,
            )

    await run_doc.write_job_doc(
        {
            "job_id": job_id,
            "user_id": user_id,
            "mode": "extract_upload",
            "status": "completed",
            "stage": "completed",
            "progress": 1.0,
            "error": None,
            "result": {"upload_ids": upload_ids},
        }
    )


def _delete_graph_data(graph_ids: list[str]) -> None:
    """Best-effort Neo4j cleanup for a deleted account (plan §12).

    KNOWN GAP: the graph layer writes a ``graph_id`` property on its nodes and
    relations (``src/graph/normalization.py``) but exposes **no**
    delete-by-graph-id operation, and inventing a new Neo4j API is out of scope
    for this task. Log the ids so an operator can clear them; do not pretend.
    """
    if not graph_ids:
        return
    logger.warning(
        "account delete: Neo4j data for graph_ids %s was NOT removed — the graph "
        "layer has no delete-by-graph-id API (known gap)",
        graph_ids,
    )


async def _account_delete_core(job_id: str, payload: dict[str, Any]) -> None:
    """Purge one account's data (plan §12): rows, then objects, then the graph.

    The user row itself is kept — the route already stamped ``disabled_at`` (the
    soft delete); this removes everything that hangs off it. The job's own
    ``jobs`` row belongs to the user, so it is deleted too and the lifecycle's
    terminal write is a harmless no-op.
    """
    from sqlalchemy import delete, select

    from src.db.engine import get_session_factory
    from src.db.models import Dataset, Job, Run, RunEvent, Upload, UserSession
    from src.ingest import storage

    owner = uuid.UUID(str(payload["user_id"]))
    async with get_session_factory()() as session:
        graph_ids = [
            row
            for row in (
                await session.execute(
                    select(Dataset.graph_id).where(
                        Dataset.user_id == owner, Dataset.graph_id.is_not(None)
                    )
                )
            ).scalars()
            if row is not None
        ]
        # Dependency order (run_events → jobs → runs → uploads → sessions) so no
        # delete relies on a cascade being configured.
        await session.execute(
            delete(RunEvent).where(
                RunEvent.run_id.in_(select(Run.id).where(Run.user_id == owner))
            )
        )
        await session.execute(delete(Job).where(Job.user_id == owner))
        await session.execute(delete(Run).where(Run.user_id == owner))
        await session.execute(delete(Upload).where(Upload.user_id == owner))
        await session.execute(delete(UserSession).where(UserSession.user_id == owner))
        await session.commit()

    removed = await asyncio.to_thread(storage.delete_prefix, f"{owner}/")
    # Export zips hold the same personal data and must not outlive the account.
    removed += await asyncio.to_thread(storage.delete_prefix, f"exports/{owner}/")
    logger.info("account delete %s: removed %d object(s)", owner, removed)
    _delete_graph_data(graph_ids)


def _run_json(run) -> dict[str, Any]:
    return {
        "run_id": str(run.id),
        "query": run.query,
        "status": run.status,
        "verdict": run.verdict,
        "confidence": run.confidence,
        "created_at": run.created_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


def _upload_json(upload) -> dict[str, Any]:
    return {
        "upload_id": str(upload.id),
        "object_key": upload.object_key,
        "bytes": upload.bytes,
        "mime": upload.mime,
        "sha256": upload.sha256,
        "created_at": upload.created_at.isoformat(),
        "has_text": bool(upload.extracted_text),
    }


async def _account_export_core(job_id: str, payload: dict[str, Any]) -> None:
    """Build the account's data zip and store it under ``exports/`` (plan §12)."""
    import io
    import zipfile

    from sqlalchemy import select

    from src.api import run_doc
    from src.db.engine import get_session_factory
    from src.db.models import Job, Run, Upload
    from src.ingest import storage

    owner = uuid.UUID(str(payload["user_id"]))
    async with get_session_factory()() as session:
        # The account-lifecycle jobs write their own run rows; they are not the
        # user's data and must not appear in their export.
        runs = (
            (
                await session.execute(
                    select(Run)
                    .join(Job, Job.id == Run.id)
                    .where(
                        Run.user_id == owner,
                        Job.kind.notin_(("account_export", "account_delete")),
                    )
                )
            )
            .scalars()
            .all()
        )
        uploads = (
            (await session.execute(select(Upload).where(Upload.user_id == owner)))
            .scalars()
            .all()
        )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "runs.json",
            json.dumps([_run_json(run) for run in runs], indent=2, default=str),
        )
        archive.writestr(
            "uploads.json",
            json.dumps(
                [_upload_json(upload) for upload in uploads], indent=2, default=str
            ),
        )
        for upload in uploads:
            if upload.extracted_text:
                archive.writestr(f"texts/{upload.id}.txt", upload.extracted_text)

    key = f"exports/{owner}/{job_id}.zip"
    data = buffer.getvalue()
    await asyncio.to_thread(storage.put_bytes, key, data)
    await run_doc.write_job_doc(
        {
            "job_id": job_id,
            "user_id": str(owner),
            "mode": "account_export",
            "status": "completed",
            "stage": "completed",
            "progress": 1.0,
            "error": None,
            "result": {"object_key": key, "bytes": len(data)},
        }
    )


#: kind → async core. The tests swap a core out to drive the lifecycle without
#: standing up Neo4j/LLM.
CORES = {
    "debate": _debate_core,
    "ontology": _ontology_core,
    "build_graph": _build_graph_core,
    "normalize_graph": _normalize_graph_core,
    "extract_upload": _extract_upload_core,
    "account_delete": _account_delete_core,
    "account_export": _account_export_core,
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


def extract_upload(job_id: str, payload: dict[str, Any]) -> None:
    asyncio.run(execute("extract_upload", job_id, payload))


def account_delete(job_id: str, payload: dict[str, Any]) -> None:
    asyncio.run(execute("account_delete", job_id, payload))


def account_export(job_id: str, payload: dict[str, Any]) -> None:
    asyncio.run(execute("account_export", job_id, payload))


#: The RQ targets, by kind.
TASKS = {
    "debate": run_debate,
    "ontology": ontology,
    "build_graph": build_graph,
    "normalize_graph": normalize_graph,
    "extract_upload": extract_upload,
    "account_delete": account_delete,
    "account_export": account_export,
}
