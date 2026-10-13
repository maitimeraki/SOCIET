"""Application settings, read from environment variables only (12-factor).

Lazy by design: importing this module must never fail. DATABASE_URL is a
required secret with no committed default (R11), so its requiredness is
enforced at the point of use (engine, alembic env) — not at import time.
"""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode


class Settings(BaseSettings):
    env: Literal["dev", "staging", "prod"] = "dev"
    database_url: str | None = None
    redis_url: str = "redis://localhost:6379/0"
    session_ttl_days: int = 30
    cookie_secure: bool = False  # env COOKIE_SECURE; False for plain-HTTP dev
    ws_ticket_ttl_seconds: int = 30

    # --- API edge (env CORS_ALLOWED_ORIGINS / ALLOWED_HOSTS are comma-separated;
    # NoDecode keeps pydantic-settings from JSON-decoding them).
    cors_allowed_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    # "testserver" is required: the FastAPI TestClient dials that host.
    allowed_hosts: Annotated[list[str], NoDecode] = ["localhost", "127.0.0.1", "testserver"]
    max_json_bytes: int = 1_048_576  # 1 MB, JSON bodies only
    llm_probe_timeout_seconds: int = 5  # budget for one readiness probe
    rate_limit_login: str = "5/minute"
    rate_limit_signup: str = "10/hour"
    rate_limit_debate_enqueue: str = "20/hour"

    @field_validator("cors_allowed_origins", "allowed_hosts", mode="before")
    @classmethod
    def _split_comma_separated(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
