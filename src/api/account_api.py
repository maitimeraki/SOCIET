"""Account lifecycle: delete and export (plan §12).

New surface, so v1-only (R15): ``/api/v1/account``. Both operations are
owner-scoped (the authenticated user acts on their own account) and both hand
the heavy lifting to an async job (Task 6 pattern) — the request does the
immediate, reversible-in-a-sense part and returns 202 with the job id.

Delete is the one irreversible operation, so it demands an explicit
confirmation: the body must echo the account email.
"""

import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.jobs_api import enqueue_or_http
from src.audit import client_ip, record
from src.auth.cookies import verify_csrf
from src.auth.deps import current_user
from src.auth.service import normalize_email
from src.db.engine import get_db
from src.db.models import User, UserSession

router = APIRouter(
    prefix="/api/v1/account",
    tags=["account"],
    dependencies=[Depends(verify_csrf)],
)


class DeleteAccountRequest(BaseModel):
    confirm: EmailStr


def _correlation_id(request: Request) -> str | None:
    return getattr(request.state, "correlation_id", None)


async def _disable_and_revoke(db: AsyncSession, user: User) -> None:
    """Soft-delete immediately: no new logins, every session dead (plan §12)."""
    now = datetime.datetime.now(datetime.UTC)
    user.disabled_at = now
    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await db.commit()


@router.delete("", status_code=202)
async def delete_account(
    body: DeleteAccountRequest,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disable the account and queue its purge.

    The body's ``confirm`` must equal the account email (a 400 otherwise). A
    second delete is a 409: the account is already disabled — though in practice
    the revoked sessions mean a repeat call is refused 401 at auth first.
    """
    if normalize_email(body.confirm) != normalize_email(user.email):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "confirmation_mismatch",
                "message": "The confirmation must match your account email.",
            },
        )
    if user.disabled_at is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "account_already_deleted",
                "message": "This account is already being deleted.",
            },
        )

    await _disable_and_revoke(db, user)
    try:
        job_id = await enqueue_or_http(
            "account_delete",
            {
                "user_id": str(user.id),
                "correlation_id": _correlation_id(request),
            },
        )
    except Exception:
        # The purge never queued: leave the account usable rather than stranded
        # disabled with its data intact (its sessions are already revoked, so
        # the owner simply logs in again).
        user.disabled_at = None
        await db.commit()
        raise

    await record(
        db,
        "account_delete",
        user_id=user.id,
        target=str(user.id),
        ip=client_ip(request),
    )
    return {"job_id": job_id, "status": "queued"}


@router.get("/export", status_code=202)
async def export_account(
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Queue the export job; the zip's download URL comes from the job read."""
    job_id = await enqueue_or_http(
        "account_export",
        {
            "user_id": str(user.id),
            "correlation_id": _correlation_id(request),
        },
    )
    await record(
        db,
        "account_export",
        user_id=user.id,
        target=str(user.id),
        ip=client_ip(request),
    )
    return {"job_id": job_id, "status": "queued"}
