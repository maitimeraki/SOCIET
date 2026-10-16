"""Job surface: enqueue mapping and cancellation (plan §5).

The enqueue routes in ``debate_api``/``api_server`` share ``enqueue_or_http`` so
the cap and validation failures leave as the one error shape (plan §6), and
cancellation lives here for the same reason the other areas have their own
router (R15: mounted at ``/api/v1/jobs`` and the legacy ``/simulate/jobs``).
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api import run_doc
from src.audit import client_ip
from src.audit import record as audit_record
from src.auth.cookies import verify_csrf
from src.auth.deps import current_user, require_owner
from src.db.engine import get_db
from src.db.models import User
from src.jobs import queue as jobs_queue

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/jobs", tags=["jobs"], dependencies=[Depends(verify_csrf)]
)


async def get_job_status(job_id: str, user: User):
    """A job's status doc, owner-checked.

    An export job's result carries its object key; a short-lived download URL is
    minted at read time (plan §12). Best-effort: a storage blip must not break
    job polling — the URL is simply absent until the next read.
    """
    doc = await run_doc.read_job_doc(job_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Job not found")
    await require_owner(doc.get("user_id"), user)
    result = doc.get("result")
    key = result.get("object_key") if isinstance(result, dict) else None
    if key:
        from src.config.settings import get_settings
        from src.ingest.storage import presigned_url

        try:
            doc["download_url"] = await asyncio.to_thread(
                presigned_url, key, get_settings().export_url_ttl_seconds
            )
        except Exception as exc:
            logger.warning("could not presign export %s: %s", key, exc)
    return doc


# The v1-canonical status read: `/api/v1/jobs/{id}` (and the legacy
# `/simulate/jobs/{id}` twin — `simulate_router` registers the same function).
@router.get("/{job_id}")
async def get_job(job_id: str, user: User = Depends(current_user)):
    return await get_job_status(job_id, user)


async def enqueue_or_http(kind: str, payload: dict) -> str:
    """``queue.enqueue`` with the uniform HTTP mapping for its two refusals."""
    try:
        return await jobs_queue.enqueue(kind, payload)
    except jobs_queue.JobLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail={"code": "job_limit_exceeded", "message": str(exc)},
            headers={"Retry-After": str(jobs_queue.RETRY_AFTER_SECONDS)},
        ) from exc
    except jobs_queue.JobValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "validation_error", "message": str(exc)},
        ) from exc


@router.delete("/{job_id}")
async def cancel_job(
    job_id: str,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a job: queued ones immediately, running ones at their next boundary.

    Owner-checked (a foreign id is a 404 — existence is not leaked); a job that
    already reached a terminal state is a 409, not a silent no-op.
    """
    head = await run_doc.read_run_head(job_id)
    if head is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "job_not_found", "message": "No job with that id."},
        )
    await require_owner(head.get("user_id"), user)

    status = head.get("status")
    if status in run_doc.TERMINAL_STATUSES:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "job_not_cancellable",
                "message": f"The job is already {status}.",
            },
        )

    # The flag is set in both cases: a queued job may be picked up by the worker
    # between this read and its cancelled row, and the flag makes that a no-op.
    jobs_queue.set_cancel(job_id)
    await audit_record(
        db, "run_cancel", user_id=user.id, target=job_id, ip=client_ip(request)
    )
    if status == "queued":
        await run_doc.set_job_status(job_id, "cancelled")
        logger.info("cancelled queued job %s", job_id)
        return {"job_id": job_id, "status": "cancelled"}

    logger.info("cancel requested for running job %s", job_id)
    return {"job_id": job_id, "status": "cancelling"}
