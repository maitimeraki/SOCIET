"""Async SQLAlchemy engine and session factory.

The engine is created lazily on first use from ``DATABASE_URL`` (via
``get_settings()``) so importing this module never requires the secret to be
set. Using it while unset raises a clear error naming the variable.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config.settings import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _database_url() -> str:
    url = get_settings().database_url
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. It is a required secret with no committed "
            "default — export DATABASE_URL=postgresql+psycopg://user:password@host:5432/dbname "
            "before using the database."
        )
    return url


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(_database_url())
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request."""
    async with get_session_factory()() as session:
        yield session
