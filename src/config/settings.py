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
    rate_limit_verdict_retry: str = "10/hour"

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
    # legal + entity + Razorpay are ready; the free plan is the entitlement while off.
    billing_enabled: bool = False
    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None
    razorpay_webhook_secret: str | None = None
    razorpay_plan_starter_inr: str | None = None
    razorpay_plan_starter_usd: str | None = None
    razorpay_plan_studio_inr: str | None = None
    razorpay_plan_studio_usd: str | None = None
    # Monthly cycles before a subscription completes; the user then drops to free.
    razorpay_subscription_total_count: int = 120
    # Where the SPA sends the browser back to after checkout.
    app_base_url: str = "http://localhost:5173"

    # --- Transactional email (plan §7): a bare httpx POST, no framework. An
    # empty key is the dev/staging log sink; prod refuses to boot without one.
    email_api_url: str = "https://api.resend.com/emails"
    email_api_key: str | None = None
    email_from: str = "no-reply@societas.app"
    email_verification_ttl_seconds: int = 86_400  # 24 h (link)
    password_reset_ttl_seconds: int = 3_600  # 1 h
    rate_limit_email: str = "3/hour"

    # --- Email verification codes. The short code is the primary gate; the
    # link stays as a one-click fallback inside the same mail.
    require_email_verification: bool = True
    email_code_ttl_seconds: int = 600  # 10 min
    email_code_resend_seconds: int = 60
    email_code_max_attempts: int = 5
    email_code_hourly_limit: int = 5
    rate_limit_verify_code: str = "10/minute"

    # --- OAuth sign-in (GitHub and Google). Empty credentials disable a
    # provider; the redirect URI must be registered at the provider as
    # {oauth_redirect_base or app_base_url}/api/v1/auth/oauth/{provider}/callback.
    github_client_id: str | None = None
    github_client_secret: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    oauth_redirect_base: str | None = None
    oauth_state_ttl_seconds: int = 600
    rate_limit_oauth: str = "20/minute"
    billing_reconcile_cron: str = "17 * * * *"  # hourly at :17
    billing_lease_sweep_cron: str = "*/10 * * * *"  # every 10 minutes
    legal_entity_name: str = ""
    legal_contact_email: str = "hello@societas.app"

    plan_free_units: int = 1_000
    plan_starter_units: int = 8_000
    plan_studio_units: int = 16_000
    plan_enterprise_units: int = 80_000

    # Plan rate card — the public pricing surface and the server's one source.
    # INR figures are PLACEHOLDERS until the rupee price is set.
    plan_starter_price_inr: int = 999
    plan_studio_price_inr: int = 1_999
    plan_starter_price_usd: int = 10
    plan_studio_price_usd: int = 20
    plan_enterprise_price_label: str = "Custom"

    # The unit hold a graph job takes at enqueue; the worker re-checks it before
    # any LLM call and settlement releases only what the job actually holds.
    graph_job_reserve_units: int = 2_000

    # The unit hold a verdict retry takes at enqueue. None derives it: the report's
    # maximum attempts times the typical units one debate call settles (debate_api).
    verdict_retry_reserve_units: int | None = None

    plan_free_max_agents: int = 10
    plan_starter_max_agents: int = 12
    plan_studio_max_agents: int = 12
    plan_enterprise_max_agents: int = 12

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

        if self.env == "prod" and self.app_base_url.rstrip("/").startswith(
            ("http://localhost", "http://127.0.0.1")
        ):
            raise ValueError("APP_BASE_URL must be the public origin in production")

        for provider in ("github", "google"):
            client_id = getattr(self, f"{provider}_client_id")
            client_secret = getattr(self, f"{provider}_client_secret")
            if bool(client_id) != bool(client_secret):
                raise ValueError(
                    f"{provider.upper()}_CLIENT_ID and "
                    f"{provider.upper()}_CLIENT_SECRET must be set together"
                )

        if self.email_code_ttl_seconds < 60:
            raise ValueError("email_code_ttl_seconds must be at least 60")
        if not 1 <= self.email_code_max_attempts <= 20:
            raise ValueError("email_code_max_attempts must be in [1, 20]")
        if self.email_code_resend_seconds < 10:
            raise ValueError("email_code_resend_seconds must be at least 10")
        if self.oauth_state_ttl_seconds < 60:
            raise ValueError("oauth_state_ttl_seconds must be at least 60")

        if self.billing_enabled:
            for name in (
                "razorpay_key_id",
                "razorpay_key_secret",
                "razorpay_webhook_secret",
                "razorpay_plan_starter_inr",
                "razorpay_plan_starter_usd",
                "razorpay_plan_studio_inr",
                "razorpay_plan_studio_usd",
            ):
                if not getattr(self, name):
                    raise ValueError(f"{name} is required when billing_enabled is true")

        if self.razorpay_key_id:
            prefix = "rzp_live_" if self.env == "prod" else "rzp_test_"
            if not self.razorpay_key_id.startswith(prefix):
                raise ValueError(f"razorpay_key_id must start with {prefix} in env {self.env}")

        for plan in ("free", "starter", "studio", "enterprise"):
            if getattr(self, f"plan_{plan}_units") <= 0:
                raise ValueError(f"plan_{plan}_units must be > 0")
            max_agents = getattr(self, f"plan_{plan}_max_agents")
            if not 2 <= max_agents <= 12 or max_agents % 2:
                raise ValueError(f"plan_{plan}_max_agents must be even and in [2, 12]")
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
        if self.graph_job_reserve_units < 1:
            raise ValueError("graph_job_reserve_units must be >= 1")
        if self.verdict_retry_reserve_units is not None and self.verdict_retry_reserve_units < 1:
            raise ValueError("verdict_retry_reserve_units must be >= 1 when set")
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
