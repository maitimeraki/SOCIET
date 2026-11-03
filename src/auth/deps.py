"""FastAPI dependencies: session/user resolution and ownership guards."""

import datetime
import uuid
from enum import Enum

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection
from starlette.websockets import WebSocket

from src.auth.cookies import SESSION_COOKIE
from src.auth.service import redeem_ws_ticket
from src.billing.entitlements import Entitlements, resolve_entitlements
from src.db.engine import get_db, get_session_factory
from src.db.models import User, UserSession


class Role(str, Enum):
    USER = "user"
    SUPPORT = "support"
    ADMIN = "admin"


def _unauthenticated() -> HTTPException:
    return HTTPException(status_code=401, detail="Not authenticated.")


def cookie_session_id(connection: HTTPConnection) -> uuid.UUID | None:
    """The session id carried by the sid cookie, or None if absent/malformed.

    Takes any ``HTTPConnection`` — the HTTP dependency and the WebSocket
    handshake read the same cookie off the same header.
    """
    raw = connection.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


async def _live_user(db: AsyncSession, session: UserSession | None) -> User | None:
    """The session's enabled user while the session is live, else None.

    Expired, revoked, and unknown sessions are rejected identically. Bumps
    ``last_seen_at`` on every use. The one session-validity rule — HTTP and
    the WebSocket handshake both resolve through it.
    """
    now = datetime.datetime.now(datetime.UTC)
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        return None

    session.last_seen_at = now
    await db.commit()

    user = await db.get(User, session.user_id)
    if user is None or user.disabled_at is not None:
        return None
    return user


async def current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """sid cookie → live session → enabled user, else 401."""
    sid = cookie_session_id(request)
    user = await _live_user(db, await db.get(UserSession, sid) if sid else None)
    if user is None:
        raise _unauthenticated()
    return user


async def websocket_user(websocket: WebSocket) -> User | None:
    """The WebSocket handshake identity (R4), or None for the caller to refuse.

    A live ``sid`` cookie (browser, same-origin) wins; otherwise a one-time
    ``?ticket=`` is redeemed — exactly once. Never a long-lived token.
    """
    sid = cookie_session_id(websocket)
    if sid is not None:
        async with get_session_factory()() as db:
            user = await _live_user(db, await db.get(UserSession, sid))
        if user is not None:
            return user

    ticket = websocket.query_params.get("ticket")
    if not ticket:
        return None
    user_id = await redeem_ws_ticket(ticket)
    if user_id is None:
        return None
    async with get_session_factory()() as db:
        user = await db.get(User, user_id)
        if user is None or user.disabled_at is not None:
            return None
        return user


def _as_uuid(value: uuid.UUID | str | None) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def require_role(*allowed: Role | str):
    """Router-level guard (never per handler): 403 unless the user holds a role."""

    async def _dep(user: User = Depends(current_user)) -> User:
        if user.role not in {a.value if isinstance(a, Role) else a for a in allowed}:
            raise HTTPException(status_code=403, detail="Forbidden.")
        return user

    return _dep


async def get_entitlements(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> Entitlements:
    return await resolve_entitlements(db, user=user)


async def require_owner(resource_user_id: uuid.UUID | str | None, user: User) -> None:
    """404 (not 403) when the resource belongs to someone else — existence is
    not leaked.

    Takes the owner as stored (documents carry the uuid as a string); a missing
    owner — a legacy doc predating guards (R14) — or a malformed one is not
    found.
    """
    if _as_uuid(resource_user_id) != user.id:
        raise HTTPException(status_code=404, detail="Not found.")
