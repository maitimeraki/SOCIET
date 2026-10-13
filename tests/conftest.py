"""Shared fixtures for the DB-backed tests.

Opt-in only (no autouse) — requesting ``db`` opts a test into the Postgres
helper. It also disposes the engine after each test: pytest-asyncio gives
every test a fresh event loop, and a pooled async connection cannot be reused
across loops.
"""

import os

# The suite must never trip a rate limit, and every ASGI test client shares the
# 127.0.0.1 bucket. Set before any app import (conftest loads first; the limits
# are read per request via get_settings(), which is lru_cached).
os.environ.setdefault("RATE_LIMIT_LOGIN", "1000/minute")
os.environ.setdefault("RATE_LIMIT_SIGNUP", "10000/hour")
os.environ.setdefault("RATE_LIMIT_DEBATE_ENQUEUE", "10000/hour")

import pytest_asyncio
from sqlalchemy import delete

from src.db.engine import get_engine, get_session_factory
from src.db.models import User

# Auth tests create accounts under this domain; the fixture clears them before
# and after each test so reruns never collide on the unique email.
TEST_EMAIL_LIKE = "auth-test-%@example.com"


async def _purge(session) -> None:
    await session.execute(delete(User).where(User.email.like(TEST_EMAIL_LIKE)))
    await session.commit()


@pytest_asyncio.fixture
async def db():
    factory = get_session_factory()
    async with factory() as session:
        await _purge(session)
        yield session
    async with factory() as session:
        await _purge(session)
    await get_engine().dispose()


@pytest_asyncio.fixture
async def redis_reset():
    """Close the cached Redis client after the test so the next test's fresh
    event loop does not reuse a pool bound to a dead loop."""
    from src.auth import service

    yield
    await service.close_redis()
