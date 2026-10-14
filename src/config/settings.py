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
    allowed_hosts: Annotated[list[str], NoDecode] = [
        "localhost",
        "127.0.0.1",
        "testserver",
    ]
    max_json_bytes: int = 1_048_576  # 1 MB, JSON bodies only
    llm_probe_timeout_seconds: int = 5  # budget for one readiness probe
    rate_limit_login: str = "5/minute"
    rate_limit_signup: str = "10/hour"
    rate_limit_debate_enqueue: str = "20/hour"

    # --- Job queue (plan §5). ``rq`` dispatches to the Redis-backed worker
    # (Task 8's compose); ``inline`` runs the same task in-process — the dev
    # fallback on Windows, where RQ's fork-based workers cannot run.
    queue_mode: Literal["rq", "inline"] = "rq"
    job_timeout_debate_seconds: int = 1800
    job_timeout_graph_seconds: int = 900
    max_jobs_per_user: int = 3
    job_retry_max: int = 2
    job_retry_intervals: Annotated[list[int], NoDecode] = [30, 120]

    # --- Object storage (MinIO in dev, plan §7). Lazy by design: importing
    # settings never touches S3 — only a real storage call fails when the
    # bucket is unreachable. The access/secret defaults are the MinIO dev
    # defaults matching compose's `minio` service — dev-only; production
    # overrides them via the environment.
    s3_endpoint_url: str = "http://127.0.0.1:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "societas-uploads"
    s3_region: str = "us-east-1"

    # --- Per-user upload quota (plan §7): usage is SUM(bytes)/COUNT(*) over
    # the user's `uploads` rows for the current calendar month.
    upload_quota_bytes_month: int = 104_857_600  # 100 MB
    upload_quota_files_month: int = 200

    # --- Bounded extraction (plan §7): the worker runs every extractor in an
    # isolated child process with a hard wall-clock timeout and an output cap.
    extract_timeout_seconds: int = 30
    extract_max_output_bytes: int = 5_000_000

    # --- Account lifecycle (plan §12): how long an export's presigned download
    # URL stays valid. Short by design — the URL is minted per read.
    export_url_ttl_seconds: int = 900

    # --- Observability (plan §10). Off by default locally; compose sets
    # METRICS_ENABLED=true. Tracing (OTEL_EXPORTER_OTLP_ENDPOINT) and error
    # reporting (SENTRY_DSN) are read from the environment by src/observability.
    metrics_enabled: bool = False
    metrics_port: int = 9100

    # --- Retention (plan §12), in days. The purge ships as a script
    # (``scripts/purge_retention.py``) and an RQ-schedulable task
    # (``src.jobs.tasks.purge_retention``); scheduling it is deployment's job.
    retention_runs_days: int = 365
    retention_raw_uploads_days: int = 30
    retention_audit_days: int = 365

    # --- Graceful shutdown (plan §9): the bounded window in-flight jobs get to
    # finish before the API process exits. Never blocks past it.
    shutdown_drain_seconds: int = 30

    @field_validator(
        "cors_allowed_origins", "allowed_hosts", "job_retry_intervals", mode="before"
    )
    @classmethod
    def _split_comma_separated(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
