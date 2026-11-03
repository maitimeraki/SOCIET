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

# Stage construction requires an extraction key; the tests mock every LLM call
# and never dial NVIDIA. Local .env files provide one, CI does not, so a blank
# or absent value gets a non-secret placeholder before config_llm reads env.
# EXTRACTION_API_KEY outranks NVIDIA_NIM_API_KEY in provider resolution, so it
# is only injected when a non-default provider is selected — otherwise the
# unchanged NIM-credential tests would see the placeholder instead.
if not os.environ.get("NVIDIA_NIM_API_KEY"):
    os.environ["NVIDIA_NIM_API_KEY"] = "test-nim-key"
if (
    os.environ.get("EXTRACTION_PROVIDER")
    and os.environ["EXTRACTION_PROVIDER"] != "nvidia_nim"
    and not os.environ.get("EXTRACTION_API_KEY")
):
    os.environ["EXTRACTION_API_KEY"] = "test-extraction-key"

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
