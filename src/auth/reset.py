"""Password-reset tokens and the reset write path.

Tokens are single-use and TTL-bounded in Redis. ``reset_password`` needs no
old password (the token is the proof) and revokes every session.
"""

import asyncio
import datetime
import logging
import secrets
import uuid

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.service import (
    MIN_PASSWORD_LENGTH,
    get_redis,
    hash_password,
)
from src.config.settings import get_settings
from src.db.models import User, UserSession
from src.email.service import reset_message, send

logger = logging.getLogger(__name__)

PREFIX = "password_reset"
_INVALID_TOKEN = "This link is invalid or has expired."


async def issue_reset_token(user_id: uuid.UUID) -> str:
    token = secrets.token_urlsafe(32)
    await get_redis().setex(
        f"{PREFIX}:{token}", get_settings().password_reset_ttl_seconds, str(user_id)
    )
    return token


async def redeem_reset_token(token: str) -> uuid.UUID | None:
    """Atomically consume a token. None when missing, expired, or reused."""
    value = await get_redis().getdel(f"{PREFIX}:{token}")
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        logger.warning("Reset token payload is not a user id; discarding")
        return None


async def send_reset_email(user: User) -> None:
    token = await issue_reset_token(user.id)
    link = f"{get_settings().app_base_url}/auth/reset?token={token}"
    await send(reset_message(to=user.email, link=link))


async def reset_password(
    db: AsyncSession, user_id: uuid.UUID, new_password: str
) -> None:
    """Set a new password without the old one and revoke every session."""
    if len(new_password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
        )

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=400, detail={"code": "invalid_token", "message": _INVALID_TOKEN}
        )

    now = datetime.datetime.now(datetime.UTC)
    user.password_hash = await asyncio.to_thread(hash_password, new_password)
    user.updated_at = now
    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await db.commit()
