"""Password-reset tokens: single use, TTL-bounded, and every session revoked."""

import asyncio
import os
import uuid

import pytest

from src.auth import reset, service

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
NEW_PASSWORD = "brand-new-password"
pytestmark = [pytest.mark.asyncio]


@requires_db
@requires_redis
async def test_reset_token_redeems_once_and_revokes_every_session(db, redis_reset):
    email = f"auth-test-{uuid.uuid4().hex[:10]}@example.com"
    user, first = await service.signup(
        db, email, PASSWORD, accept_terms=True, age_confirmed=True
    )
    _, second = await service.login(db, email, PASSWORD)

    token = await reset.issue_reset_token(user.id)

    assert await reset.redeem_reset_token(token) == user.id
    assert await reset.redeem_reset_token(token) is None

    await reset.reset_password(db, user.id, NEW_PASSWORD)

    await db.refresh(user)
    await db.refresh(first)
    await db.refresh(second)
    assert service.verify_password(NEW_PASSWORD, user.password_hash)
    assert not service.verify_password(PASSWORD, user.password_hash)
    assert first.revoked_at is not None
    assert second.revoked_at is not None


@requires_redis
async def test_unknown_reset_token_returns_none(redis_reset):
    assert await reset.redeem_reset_token("never-issued") is None


@requires_redis
async def test_expired_reset_token_returns_none(redis_reset):
    token = f"expired-{uuid.uuid4().hex}"
    await service.get_redis().setex(f"password_reset:{token}", 1, str(uuid.uuid4()))

    await asyncio.sleep(1.1)

    assert await reset.redeem_reset_token(token) is None
