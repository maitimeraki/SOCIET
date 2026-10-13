"""psycopg refuses to run async on Windows' default ProactorEventLoop."""

import asyncio
import sys

import pytest_asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest_asyncio.fixture
async def redis_reset():
    """Close the cached Redis client after the test so the next test's fresh
    event loop does not reuse a pool bound to a dead loop."""
    from src.auth import service

    yield
    await service.close_redis()
