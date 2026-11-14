"""Shared fixtures for the DB-backed tests.

Opt-in only (no autouse) — requesting ``db`` opts a test into the Postgres
helper. It also disposes the engine after each test: pytest-asyncio gives
every test a fresh event loop, and a pooled async connection cannot be reused
across loops.
"""

import os
import uuid

# The suite must never trip a rate limit, and every ASGI test client shares the
# 127.0.0.1 bucket. Set before any app import (conftest loads first; the limits
# are read per request via get_settings(), which is lru_cached).
os.environ.setdefault("RATE_LIMIT_LOGIN", "1000/minute")
os.environ.setdefault("RATE_LIMIT_SIGNUP", "10000/hour")
os.environ.setdefault("RATE_LIMIT_DEBATE_ENQUEUE", "10000/hour")
os.environ.setdefault("RATE_LIMIT_EMAIL", "10000/hour")
# Counters are Redis-backed by default; a bucket left by an earlier run would
# make the login/signup limit tests non-idempotent. Tests use the documented
# single-process store unless the runner explicitly asks for another.
os.environ.setdefault("RATE_LIMIT_STORAGE_URI", "memory://")

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

import pytest
import pytest_asyncio
from sqlalchemy import delete

from src.config.settings import get_settings
from src.db.engine import get_engine, get_session_factory
from src.db.models import Dataset, User

# Auth tests create accounts under this domain; the fixture clears them before
# and after each test so reruns never collide on the unique email.
TEST_EMAIL_LIKE = "auth-test-%@example.com"


async def _purge(session) -> None:
    await session.execute(delete(User).where(User.email.like(TEST_EMAIL_LIKE)))
    await session.commit()


@pytest.fixture(autouse=True)
def _no_ambient_email_provider(monkeypatch):
    """Never send real mail from a test: the default is the dev log sink."""
    monkeypatch.delenv("EMAIL_API_KEY", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def db():
    factory = get_session_factory()
    async with factory() as session:
        await _purge(session)
        yield session
    async with factory() as session:
        await _purge(session)
    await get_engine().dispose()
    # Signup now touches Redis (it sends a verification email); close the shared
    # client in this test's loop so the next test never reuses a pool bound to a
    # dead one.
    from src.auth import service

    await service.close_redis()


@pytest_asyncio.fixture
async def owned_corpus():
    """Make a `datasets` row owned by a user; returns `async (user_id) -> uuid`.

    A debate names its corpus by `graph_id`, and the route accepts only a corpus
    the caller owns, so each debate-posting test makes one for its own account.
    Account teardown removes the row (`datasets.user_id` cascades).
    """

    async def _make(user_id) -> uuid.UUID:
        corpus = uuid.uuid4()
        async with get_session_factory()() as session:
            session.add(
                Dataset(id=corpus, user_id=uuid.UUID(str(user_id)), name="Test corpus")
            )
            await session.commit()
        return corpus

    return _make


@pytest_asyncio.fixture
async def redis_reset():
    """Close the cached Redis client after the test so the next test's fresh
    event loop does not reuse a pool bound to a dead loop."""
    from src.auth import service

    yield
    await service.close_redis()


class RecordingDriver:
    """A fake Neo4j driver that records every (query, params) pair.

    Scope guards (audit C1) assert the dataset predicate and its bound
    `dataset_id` on what a reader actually sends, so the driver is the seam.
    """

    def __init__(self):
        from unittest.mock import AsyncMock, MagicMock

        self.calls: list[tuple[str, dict]] = []
        result = MagicMock()
        result.data = AsyncMock(return_value=[])
        # A row, so get_entity_context gets past the entity fetch and runs the
        # neighbour and provenance queries too.
        result.single = AsyncMock(
            return_value={"n": {"id": "a", "name": "a"}, "label": "Persona"}
        )
        session = MagicMock()

        async def run(query, **params):
            self.calls.append((str(query), params))
            return result

        session.run = run
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        self.driver = MagicMock()
        self.driver.session = MagicMock(return_value=session)


@pytest.fixture
def recorder() -> RecordingDriver:
    return RecordingDriver()
