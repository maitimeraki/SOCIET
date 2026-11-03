"""Email-verification tokens: single-use, TTL-bounded, Redis-backed.

The token is the key, the user id the value; redemption is GETDEL so a token
works exactly once. It is never a bearer credential beyond this one action.
"""

import logging
import secrets
import uuid

from src.auth.service import get_redis
from src.config.settings import get_settings
from src.db.models import User
from src.email.service import send, verification_message

logger = logging.getLogger(__name__)

PREFIX = "email_verify"


async def issue_verification_token(user_id: uuid.UUID) -> str:
    token = secrets.token_urlsafe(32)
    await get_redis().setex(
        f"{PREFIX}:{token}",
        get_settings().email_verification_ttl_seconds,
        str(user_id),
    )
    return token


async def redeem_verification_token(token: str) -> uuid.UUID | None:
    """Atomically consume a token. None when missing, expired, or reused."""
    value = await get_redis().getdel(f"{PREFIX}:{token}")
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        logger.warning("Verification token payload is not a user id; discarding")
        return None


async def send_verification_email(user: User) -> None:
    token = await issue_verification_token(user.id)
    link = f"{get_settings().app_base_url}/auth/verify?token={token}"
    await send(verification_message(to=user.email, link=link))
