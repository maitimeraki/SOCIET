"""Audit log writes (plan §8).

One function, ``record``, appends an ``audit_log`` row. It is **best-effort by
design**: an audit write that fails is logged at ``error`` and swallowed, so a
full disk, a dropped connection, or a closed session can never break the
business operation the caller just completed. Business errors are never
swallowed here — this module only ever touches the audit row.
"""

import logging
import uuid

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AuditLog

logger = logging.getLogger(__name__)

#: The audited actions. ``me`` and other read-only noise is deliberately absent.
ACTIONS = frozenset(
    {
        "login",
        "logout",
        "password_change",
        "session_revoke",
        "run_create",
        "run_cancel",
        "plan_denied",
        "plan_clamp",
        "plan_change",
        "units_reserve",
        "units_denied",
        "units_release",
        "upload",
        "upload_delete",
        "account_delete",
        "account_export",
        "ws_ticket_issue",
    }
)


def client_ip(request: Request) -> str | None:
    """The caller's address, resolved the same way the rate limiter buckets it."""
    from src.api.client_ip import resolved_client_ip

    peer = request.client.host if request.client else None
    return resolved_client_ip(peer, request.headers.get("x-forwarded-for"))


def _as_uuid(value: object) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


async def record(
    db: AsyncSession,
    action: str,
    user_id: object = None,
    target: str | None = None,
    ip: str | None = None,
    meta: dict | None = None,
) -> None:
    """Append one audit row; never raise.

    A failure is logged and rolled back so the caller's session is usable for
    whatever it does next. Callers commit their business work first, so the
    rollback can only ever discard the audit insert itself.
    """
    try:
        db.add(
            AuditLog(
                # audit_log.id has no server default (unlike the other tables),
                # so the primary key is minted here.
                id=uuid.uuid4(),
                user_id=_as_uuid(user_id),
                action=action,
                target=target,
                ip=ip,
                meta=meta,
            )
        )
        await db.commit()
    except Exception as exc:
        logger.error("audit write failed for action %r: %s", action, exc)
        try:
            await db.rollback()
        except Exception:
            # A session too broken to roll back is exactly the case this guard
            # exists for; the request must still proceed.
            pass
