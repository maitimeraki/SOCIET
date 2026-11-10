"""Email-verification tokens: single use, TTL-bounded, Redis-backed."""

import asyncio
import os
import uuid

import pytest

from src.auth import service, verify

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)


def _redis_available() -> bool:
    try:
        import redis

        from src.config.settings import get_settings

        client = redis.Redis.from_url(
            get_settings().redis_url, socket_connect_timeout=1
        )
        try:
            return bool(client.ping())
        finally:
            client.close()
    except Exception:
        return False


requires_redis = pytest.mark.skipif(
    not _redis_available(), reason="Redis is not reachable"
)

PASSWORD = "hunter2hunter2"
pytestmark = [pytest.mark.asyncio]


@requires_db
@requires_redis
async def test_verification_token_redeems_once(db, redis_reset):
    email = f"auth-test-{uuid.uuid4().hex[:10]}@example.com"
    user, _ = await service.signup(
        db, email, PASSWORD, accept_terms=True, age_confirmed=True
    )

    token = await verify.issue_verification_token(user.id)

    assert await verify.redeem_verification_token(token) == user.id
    assert await verify.redeem_verification_token(token) is None


@requires_redis
async def test_unknown_verification_token_returns_none(redis_reset):
    assert await verify.redeem_verification_token("never-issued") is None


@requires_redis
async def test_expired_verification_token_returns_none(redis_reset):
    token = f"expired-{uuid.uuid4().hex}"
    await service.get_redis().setex(f"email_verify:{token}", 1, str(uuid.uuid4()))

    await asyncio.sleep(1.1)

    assert await verify.redeem_verification_token(token) is None
