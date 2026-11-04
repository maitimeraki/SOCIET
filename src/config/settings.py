"""Application settings, read from environment variables only (12-factor).

Lazy by design: importing this module must never fail. DATABASE_URL is a
required secret with no committed default (R11), so its requiredness is
enforced at the point of use (engine, alembic env) — not at import time.
"""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    # Resolved once at construction and never mutated afterwards: a running
    # process cannot silently change its own plan table or trust boundary.
    model_config = SettingsConfigDict(frozen=True)

    env: Literal["dev", "staging", "prod"] = "dev"
    database_url: str | None = None
    redis_url: str = "redis://localhost:6379/0"
    session_ttl_days: int = 30
    # env COOKIE_SECURE; unset → Secure in prod, plain-HTTP-friendly elsewhere.
    cookie_secure: bool = False
    ws_ticket_ttl_seconds: int = 30

    @model_validator(mode="before")
    @classmethod
    def _secure_cookie_in_prod(cls, data: object) -> object:
        """Default the ``Secure`` flag to True under ``ENV=prod`` unless set.

        An explicit COOKIE_SECURE (env or kwarg) always wins; the default only
        applies when the operator left it unset, so a prod deploy never ships a
        non-Secure ``sid`` cookie.
        """
        if isinstance(data, dict) and data.get("cookie_secure") is None:
            data["cookie_secure"] = data.get("env") == "prod"
        return data

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
    # `X-Forwarded-For` is honored only when the direct peer is listed here
    # (or the list contains "*"). Empty in dev: no proxy, no trust.
    forwarded_allow_ips: Annotated[list[str], NoDecode] = []
    max_json_bytes: int = 1_048_576  # 1 MB, JSON bodies only
    llm_probe_timeout_seconds: int = 5  # budget for one readiness probe
    # Empty -> REDIS_URL (shared buckets across replicas); "memory://" is the
    # explicit single-process / test opt-out.
    rate_limit_storage_uri: str = ""
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

    # --- Billing and entitlements (plan §4, §6). billing_enabled stays False until
    # legal + entity + Stripe are ready; the free plan is the entitlement while off.
    billing_enabled: bool = False
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_starter: str | None = None
    stripe_price_studio: str | None = None
    # Where Checkout/Portal send the browser back to (the SPA origin).
    app_base_url: str = "http://localhost:5173"

    # --- Transactional email (plan §7): a bare httpx POST, no framework. An
    # empty key is the dev/staging log sink; prod refuses to boot without one.
    email_api_url: str = "https://api.resend.com/emails"
    email_api_key: str | None = None
    email_from: str = "no-reply@societas.app"
    email_verification_ttl_seconds: int = 86_400  # 24 h
    password_reset_ttl_seconds: int = 3_600  # 1 h
    rate_limit_email: str = "3/hour"
    stripe_webhook_tolerance_seconds: int = 300
    billing_reconcile_cron: str = "17 * * * *"  # hourly at :17
    billing_lease_sweep_cron: str = "*/10 * * * *"  # every 10 minutes
    legal_entity_name: str = ""
    legal_contact_email: str = "hello@societas.app"

    plan_free_units: int = 1_000
    plan_starter_units: int = 8_000
    plan_studio_units: int = 16_000
    plan_enterprise_units: int = 80_000

    plan_free_max_agents: int = 10
    plan_starter_max_agents: int = 20
    plan_studio_max_agents: int = 20
    plan_enterprise_max_agents: int = 40

    plan_free_max_rounds: int = 3
    plan_starter_max_rounds: int = 4
    plan_studio_max_rounds: int = 4
    plan_enterprise_max_rounds: int = 4

    unit_tokens: int = 1_000  # internal meter; never rendered
    chars_per_unit: int = 2_000  # pre-flight estimate only
    unit_cost_usd: float = 0.0002  # internal only; margin checks
    billing_reservation_lease_seconds: int = 3_600

    @model_validator(mode="after")
    def _validate_billing(self) -> "Settings":
        if self.env == "prod" and not self.email_api_key:
            raise ValueError("EMAIL_API_KEY is required in production")

        if self.billing_enabled:
            for name in (
                "stripe_secret_key",
                "stripe_webhook_secret",
                "stripe_price_starter",
                "stripe_price_studio",
            ):
                if not getattr(self, name):
                    raise ValueError(f"{name} is required when billing_enabled is true")

        for plan in ("free", "starter", "studio", "enterprise"):
            if getattr(self, f"plan_{plan}_units") <= 0:
                raise ValueError(f"plan_{plan}_units must be > 0")
            max_agents = getattr(self, f"plan_{plan}_max_agents")
            if not 2 <= max_agents <= 100 or max_agents % 2:
                raise ValueError(f"plan_{plan}_max_agents must be even and in [2, 100]")
            if not 1 <= getattr(self, f"plan_{plan}_max_rounds") <= 10:
                raise ValueError(f"plan_{plan}_max_rounds must be in [1, 10]")

        if self.unit_tokens <= 0:
            raise ValueError("unit_tokens must be > 0")
        if self.chars_per_unit <= 0:
            raise ValueError("chars_per_unit must be > 0")
        if self.unit_cost_usd < 0:
            raise ValueError("unit_cost_usd must be >= 0")
        if self.billing_reservation_lease_seconds <= 0:
            raise ValueError("billing_reservation_lease_seconds must be > 0")
        return self

    @field_validator(
        "cors_allowed_origins",
        "allowed_hosts",
        "forwarded_allow_ips",
        "job_retry_intervals",
        mode="before",
    )
    @classmethod
    def _split_comma_separated(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
