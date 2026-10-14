"""Job surface: enqueue mapping and cancellation (plan §5).

The enqueue routes in ``debate_api``/``api_server`` share ``enqueue_or_http`` so
the cap and validation failures leave as the one error shape (plan §6), and
cancellation lives here for the same reason the other areas have their own
router (R15: mounted at ``/api/v1/jobs`` and the legacy ``/simulate/jobs``).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from src.api import run_doc
from src.auth.deps import current_user, require_owner
from src.db.models import User
from src.jobs import queue as jobs_queue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


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
async def cancel_job(job_id: str, user: User = Depends(current_user)):
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
    if status == "queued":
        await run_doc.set_job_status(job_id, "cancelled")
        logger.info("cancelled queued job %s", job_id)
        return {"job_id": job_id, "status": "cancelled"}

    logger.info("cancel requested for running job %s", job_id)
    return {"job_id": job_id, "status": "cancelling"}
