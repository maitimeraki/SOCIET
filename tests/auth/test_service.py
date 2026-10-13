"""Service-level tests: hashing, accounts, sessions, password change, WS tickets.

DB tests skip without DATABASE_URL; ticket tests need Redis and skip when it is
unreachable. Everything runs against the real services and real infrastructure —
no mocks.
"""

import asyncio
import datetime
import os
import uuid

import pytest
from argon2 import PasswordHasher
from fastapi import HTTPException
from sqlalchemy import select

from src.auth import service
from src.config.settings import get_settings
from src.db.models import UserSession

requires_db = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set")


def _redis_available() -> bool:
    try:
        import redis

        client = redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=1)
        try:
            return bool(client.ping())
        finally:
            client.close()
    except Exception:
        return False


requires_redis = pytest.mark.skipif(not _redis_available(), reason="Redis is not reachable")

PASSWORD = "hunter2hunter2"


def _email() -> str:
    return f"auth-test-{uuid.uuid4().hex[:10]}@example.com"


# --- hashing (no infrastructure) -------------------------------------------


def test_hash_password_is_not_plaintext_and_verifies():
    digest = service.hash_password(PASSWORD)
    assert PASSWORD not in digest
    assert digest.startswith("$argon2id$")
    assert service.verify_password(PASSWORD, digest)
    assert not service.verify_password("wrong-password", digest)
    assert not service.verify_password(PASSWORD, "not-a-hash")


# --- accounts and sessions --------------------------------------------------


@requires_db
@pytest.mark.asyncio
async def test_signup_normalizes_email_and_rejects_duplicates(db):
    raw_email = f"  Auth-Test-{uuid.uuid4().hex[:10]}@Example.COM "
    user, session = await service.signup(db, raw_email, PASSWORD)

    assert user.email == raw_email.strip().lower()
    assert session.user_id == user.id
    assert session.expires_at > datetime.datetime.now(datetime.UTC)
    assert service.verify_password(PASSWORD, user.password_hash)

    with pytest.raises(HTTPException) as excinfo:
        await service.signup(db, raw_email.strip().upper(), PASSWORD)
    assert excinfo.value.status_code == 409


@requires_db
@pytest.mark.asyncio
async def test_signup_rejects_short_passwords(db):
    with pytest.raises(HTTPException) as excinfo:
        await service.signup(db, _email(), "short")
    assert excinfo.value.status_code == 422


@requires_db
@pytest.mark.asyncio
async def test_login_failures_are_indistinguishable(db):
    email = _email()
    await service.signup(db, email, PASSWORD)

    with pytest.raises(HTTPException) as wrong_password:
        await service.login(db, email, "wrong-password")
    with pytest.raises(HTTPException) as unknown_email:
        await service.login(db, _email(), "wrong-password")

    assert wrong_password.value.status_code == unknown_email.value.status_code == 401
    assert wrong_password.value.detail == unknown_email.value.detail == service.INVALID_CREDENTIALS


@requires_db
@pytest.mark.asyncio
async def test_login_refuses_disabled_users(db):
    email = _email()
    user, _ = await service.signup(db, email, PASSWORD)
    user.disabled_at = datetime.datetime.now(datetime.UTC)
    await db.commit()

    with pytest.raises(HTTPException) as excinfo:
        await service.login(db, email, PASSWORD)
    assert excinfo.value.status_code == 401


@requires_db
@pytest.mark.asyncio
async def test_login_rehashes_an_outdated_hash(db):
    email = _email()
    user, _ = await service.signup(db, email, PASSWORD)
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)
    user.password_hash = weak
    await db.commit()

    await service.login(db, email, PASSWORD)

    assert user.password_hash != weak
    assert service.verify_password(PASSWORD, user.password_hash)


@requires_db
@pytest.mark.asyncio
async def test_logout_deletes_the_session_row(db):
    _, session = await service.signup(db, _email(), PASSWORD)

    await service.logout(db, session.id)

    row = (
        await db.execute(select(UserSession).where(UserSession.id == session.id))
    ).scalar_one_or_none()
    assert row is None


@requires_db
@pytest.mark.asyncio
async def test_change_password_revokes_other_sessions_and_keeps_the_caller(db):
    user, caller = await service.signup(db, _email(), PASSWORD)
    _, other = await service.login(db, user.email, PASSWORD)

    await service.change_password(
        db, user.id, PASSWORD, "brand-new-password", keep_session_id=caller.id
    )

    await db.refresh(caller)
    await db.refresh(other)
    assert caller.revoked_at is None
    assert other.revoked_at is not None
    assert service.verify_password("brand-new-password", user.password_hash)


@requires_db
@pytest.mark.asyncio
async def test_change_password_rejects_a_wrong_current_password(db):
    user, caller = await service.signup(db, _email(), PASSWORD)

    with pytest.raises(HTTPException) as excinfo:
        await service.change_password(
            db, user.id, "not-the-password", "brand-new-password", keep_session_id=caller.id
        )

    assert excinfo.value.status_code == 401
    assert service.verify_password(PASSWORD, user.password_hash)


@requires_db
@pytest.mark.asyncio
async def test_list_sessions_excludes_revoked_ones(db):
    user, first = await service.signup(db, _email(), PASSWORD)
    _, second = await service.login(db, user.email, PASSWORD)

    await service.revoke_session(db, second)

    assert [s.id for s in await service.list_sessions(db, user.id)] == [first.id]


# --- WebSocket tickets (Redis) ----------------------------------------------


@requires_redis
@pytest.mark.asyncio
async def test_ws_ticket_redeems_once_then_fails(redis_reset):
    user_id = uuid.uuid4()
    ticket = await service.issue_ws_ticket(user_id)

    assert await service.redeem_ws_ticket(ticket) == user_id
    assert await service.redeem_ws_ticket(ticket) is None


@requires_redis
@pytest.mark.asyncio
async def test_ws_ticket_expires(redis_reset):
    user_id = uuid.uuid4()
    ticket = await service.issue_ws_ticket(user_id, ttl_seconds=1)

    await asyncio.sleep(1.1)

    assert await service.redeem_ws_ticket(ticket) is None
