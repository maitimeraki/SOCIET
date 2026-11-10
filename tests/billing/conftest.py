"""psycopg refuses to run async on Windows' default ProactorEventLoop."""

import asyncio
import sys

import pytest_asyncio

from src.db.engine import get_engine, get_session_factory

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest_asyncio.fixture
async def session_factory():
    yield get_session_factory()
    await get_engine().dispose()
