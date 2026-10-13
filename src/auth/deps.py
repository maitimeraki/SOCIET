"""FastAPI dependencies: session/user resolution and ownership guards."""

import datetime
import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.cookies import SESSION_COOKIE
from src.db.engine import get_db
from src.db.models import User, UserSession

def _unauthenticated() -> HTTPException:
    return HTTPException(status_code=401, detail="Not authenticated.")


def cookie_session_id(request: Request) -> uuid.UUID | None:
    """The session id carried by the sid cookie, or None if absent/malformed."""
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


async def current_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    """sid cookie → live session → enabled user, else 401.

    Expired, revoked, and unknown sessions are rejected identically. Bumps
    ``last_seen_at`` on every use.
    """
    session: UserSession | None = None
    sid = cookie_session_id(request)
    if sid is not None:
        session = await db.get(UserSession, sid)

    now = datetime.datetime.now(datetime.UTC)
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        raise _unauthenticated()

    session.last_seen_at = now
    await db.commit()

    user = await db.get(User, session.user_id)
    if user is None or user.disabled_at is not None:
        raise _unauthenticated()
    return user


async def require_owner(resource_user_id: uuid.UUID, user: User) -> None:
    """404 (not 403) when the resource belongs to someone else — existence is
    not leaked."""
    if resource_user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found.")
