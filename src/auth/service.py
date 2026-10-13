"""Auth core: argon2id password hashing, accounts, server-side sessions, WS tickets.

Sessions are rows in the ``sessions`` table (R13: the ORM lives in
``src/db/models.py``); the session id itself is the opaque cookie value.
Argon2id is CPU-bound (64 MiB per attempt), so every hash/verify call is
offloaded to a worker thread — it must never run on the event loop.
"""

import asyncio
import datetime
import logging
import secrets
import uuid
from functools import lru_cache

import redis.asyncio as aioredis
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import get_settings
from src.db.models import User, UserSession

logger = logging.getLogger(__name__)

MIN_PASSWORD_LENGTH = 8
INVALID_CREDENTIALS = "Email or password is incorrect."

# argon2-cffi defaults: time_cost=3, memory_cost=64 MiB, parallelism=4.
_hasher = PasswordHasher()

_redis: aioredis.Redis | None = None


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
        return True
    except VerifyMismatchError:
        return False
    except InvalidHashError:
        # A corrupt stored hash is a failed login, not a 500.
        logger.warning("Stored password hash is not a valid argon2 hash; treating as mismatch")
        return False


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """Verified against on unknown-email logins so the failure path costs the
    same argon2 work as a wrong password (no email enumeration by timing)."""
    return hash_password(secrets.token_urlsafe(16))


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
        )


def _new_session(
    user_id: uuid.UUID, user_agent: str | None, ip: str | None
) -> UserSession:
    now = datetime.datetime.now(datetime.UTC)
    return UserSession(
        user_id=user_id,
        expires_at=now + datetime.timedelta(days=get_settings().session_ttl_days),
        user_agent=user_agent,
        ip=ip,
    )


async def signup(
    db: AsyncSession,
    email: str,
    password: str,
    *,
    user_agent: str | None = None,
    ip: str | None = None,
) -> tuple[User, UserSession]:
    """Create the account and its first session. 409 on a duplicate email."""
    _validate_password(password)
    email = normalize_email(email)

    existing = (
        await db.execute(select(User.id).where(User.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user = User(email=email, password_hash=await asyncio.to_thread(hash_password, password))
    db.add(user)
    try:
        await db.flush()  # pulls the server-generated uuid; a concurrent duplicate lands here
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="An account with this email already exists."
        ) from exc

    session = _new_session(user.id, user_agent, ip)
    db.add(session)
    await db.commit()
    return user, session


async def login(
    db: AsyncSession,
    email: str,
    password: str,
    *,
    user_agent: str | None = None,
    ip: str | None = None,
) -> tuple[User, UserSession]:
    """Verify credentials and open a session.

    Every failure (unknown email, wrong password, disabled account) raises the
    same 401 with the same message — never reveal which one it was.
    """
    email = normalize_email(email)
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()

    if user is None:
        # Burn the same argon2 work as a real verify so response time does not
        # reveal whether the email exists.
        await asyncio.to_thread(verify_password, password, _dummy_hash())
        raise HTTPException(status_code=401, detail=INVALID_CREDENTIALS)

    if not await asyncio.to_thread(verify_password, password, user.password_hash):
        raise HTTPException(status_code=401, detail=INVALID_CREDENTIALS)
    if user.disabled_at is not None:
        raise HTTPException(status_code=401, detail=INVALID_CREDENTIALS)

    if _hasher.check_needs_rehash(user.password_hash):
        user.password_hash = await asyncio.to_thread(hash_password, password)
        user.updated_at = datetime.datetime.now(datetime.UTC)

    session = _new_session(user.id, user_agent, ip)
    db.add(session)
    await db.commit()
    return user, session


async def logout(db: AsyncSession, session_id: uuid.UUID) -> None:
    await db.execute(delete(UserSession).where(UserSession.id == session_id))
    await db.commit()


async def change_password(
    db: AsyncSession,
    user_id: uuid.UUID,
    current_password: str,
    new_password: str,
    *,
    keep_session_id: uuid.UUID | None = None,
) -> None:
    """Change the password and revoke every other session.

    ``keep_session_id`` is the caller's own session; it stays valid.
    """
    _validate_password(new_password)

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    if not await asyncio.to_thread(verify_password, current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")

    now = datetime.datetime.now(datetime.UTC)
    user.password_hash = await asyncio.to_thread(hash_password, new_password)
    user.updated_at = now

    revoke = (
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    if keep_session_id is not None:
        revoke = revoke.where(UserSession.id != keep_session_id)
    await db.execute(revoke)
    await db.commit()


async def list_sessions(db: AsyncSession, user_id: uuid.UUID) -> list[UserSession]:
    """The user's live sessions (unrevoked, unexpired), newest first."""
    now = datetime.datetime.now(datetime.UTC)
    rows = await db.execute(
        select(UserSession)
        .where(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
        .order_by(UserSession.created_at.desc())
    )
    return list(rows.scalars().all())


async def revoke_session(db: AsyncSession, session: UserSession) -> None:
    session.revoked_at = datetime.datetime.now(datetime.UTC)
    await db.commit()


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


async def close_redis() -> None:
    """Release the pooled Redis connections (shutdown, tests)."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def issue_ws_ticket(user_id: uuid.UUID, ttl_seconds: int | None = None) -> str:
    """Single-use, short-lived ticket for the WebSocket auth fallback (R4)."""
    ttl = ttl_seconds if ttl_seconds is not None else get_settings().ws_ticket_ttl_seconds
    ticket = secrets.token_urlsafe(32)
    await _get_redis().setex(f"ws_ticket:{ticket}", ttl, str(user_id))
    return ticket


async def redeem_ws_ticket(ticket: str) -> uuid.UUID | None:
    """Atomically consume a ticket (GETDEL). None when missing, expired, or reused."""
    value = await _get_redis().getdel(f"ws_ticket:{ticket}")
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        logger.warning("WS ticket payload is not a user id; discarding ticket")
        return None
