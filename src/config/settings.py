"""Application settings, read from environment variables only (12-factor).

Lazy by design: importing this module must never fail. DATABASE_URL is a
required secret with no committed default (R11), so its requiredness is
enforced at the point of use (engine, alembic env) — not at import time.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    env: Literal["dev", "staging", "prod"] = "dev"
    database_url: str | None = None
    redis_url: str = "redis://localhost:6379/0"
    session_ttl_days: int = 30
    cookie_secure: bool = False  # env COOKIE_SECURE; False for plain-HTTP dev
    ws_ticket_ttl_seconds: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
