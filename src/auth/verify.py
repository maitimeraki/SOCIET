"""Email-verification proof: a short code (primary) and a link (fallback).

Both are single-use and TTL-bounded in Redis. The code is stored only as a
SHA-256 digest keyed by the user id, so a Redis read does not hand out working
codes. Attempts are counted in the same hash; the key is deleted on success or
after the attempt bound, and a resend is throttled per account and per hour.
"""

import hashlib
import logging
import re
import secrets
import uuid

from src.auth.service import get_redis
from src.config.settings import get_settings
from src.db.models import User
from src.email.service import send, verification_message

logger = logging.getLogger(__name__)

PREFIX = "email_verify"
CODE_PREFIX = "email_verify_code"
CODE_SENT_PREFIX = "email_verify_code_sent"
CODE_COUNT_PREFIX = "email_verify_code_count"

_CODE_RE = re.compile(r"^\d{6}$")

#: `ok` — matched and consumed; `wrong` — no match, still within attempts;
#: `expired` — no live code; `too_many` — the attempt bound was reached.
CodeResult = str


class CodeThrottled(RuntimeError):
    """A code was requested again too soon, or the hourly send budget is spent."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = max(1, int(retry_after))
        super().__init__(f"verification code throttled for {self.retry_after}s")


def _hash_code(user_id: uuid.UUID, code: str) -> str:
    return hashlib.sha256(f"{user_id}:{code}".encode("utf-8")).hexdigest()


def _code_key(user_id: uuid.UUID) -> str:
    return f"{CODE_PREFIX}:{user_id}"


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


async def issue_verification_code(user_id: uuid.UUID) -> str:
    """Generate and store a six-digit code, honoring both resend budgets.

    Raises :class:`CodeThrottled` with the seconds to wait. A new code replaces
    the old one, so an earlier mail stops working the moment a resend is sent.
    """
    settings = get_settings()
    redis = get_redis()

    sent_key = f"{CODE_SENT_PREFIX}:{user_id}"
    if not await redis.set(
        sent_key, "1", nx=True, ex=settings.email_code_resend_seconds
    ):
        ttl = await redis.ttl(sent_key)
        raise CodeThrottled(ttl if ttl and ttl > 0 else settings.email_code_resend_seconds)

    count_key = f"{CODE_COUNT_PREFIX}:{user_id}"
    count = await redis.incr(count_key)
    if count == 1:
        await redis.expire(count_key, 3600)
    if count > settings.email_code_hourly_limit:
        await redis.delete(sent_key)
        raise CodeThrottled(3600)

    code = f"{secrets.randbelow(1_000_000):06d}"
    key = _code_key(user_id)
    await redis.hset(
        key,
        mapping={"hash": _hash_code(user_id, code), "attempts": "0"},
    )
    await redis.expire(key, settings.email_code_ttl_seconds)
    return code


async def redeem_verification_code(user_id: uuid.UUID, code: str) -> CodeResult:
    """Compare one submitted code in constant time and consume it on success."""
    if not _CODE_RE.fullmatch(code or ""):
        return "wrong"

    redis = get_redis()
    key = _code_key(user_id)
    expected = await redis.hget(key, "hash")
    if expected is None:
        return "expired"

    attempts = await redis.hincrby(key, "attempts", 1)
    if attempts > get_settings().email_code_max_attempts:
        await redis.delete(key)
        return "too_many"

    if secrets.compare_digest(expected, _hash_code(user_id, code)):
        await redis.delete(key)
        return "ok"
    return "wrong"


async def send_verification_email(user: User, *, code: str | None = None) -> None:
    """Send the code and a one-click link in one mail.

    ``code`` is injectable so a test can assert the message without Redis;
    production lets this function issue and store it.
    """
    settings = get_settings()
    token = await issue_verification_token(user.id)
    if code is None:
        code = await issue_verification_code(user.id)
    link = f"{settings.app_base_url.rstrip('/')}/auth/verify?token={token}"
    await send(verification_message(to=user.email, link=link, code=code))
