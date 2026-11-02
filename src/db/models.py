"""SQLAlchemy ORM models for the Postgres schema — the single ORM source (R13).

Types and defaults follow the backend plan's SQL: uuid primary keys, citext
email, jsonb payloads, inet addresses, timestamptz timestamps.
"""

import datetime
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _timestamptz_default() -> Mapped[datetime.datetime]:
    """timestamptz NOT NULL DEFAULT now() — the audit-timestamp idiom."""
    return mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = _timestamptz_default()
    updated_at: Mapped[datetime.datetime] = _timestamptz_default()
    disabled_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    role: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'user'")
    )
    plan_key: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'free'")
    )
    email_verified_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    age_confirmed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    __table_args__ = (
        CheckConstraint("role IN ('user','support','admin')", name="ck_users_role"),
    )


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime.datetime] = _timestamptz_default()
    last_seen_at: Mapped[datetime.datetime] = _timestamptz_default()
    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(INET)
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    __table_args__ = (
        Index(
            "sessions_user_id_idx",
            "user_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    graph_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = _timestamptz_default()


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="SET NULL")
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    corpus_label: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[dict | None] = mapped_column(JSONB)
    confidence: Mapped[float | None] = mapped_column(Double)
    created_at: Mapped[datetime.datetime] = _timestamptz_default()
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    # Serves the keyset-paginated history list: own runs, newest first, by
    # (created_at, id) DESC (plan §6).
    __table_args__ = (
        Index(
            "runs_user_id_created_at_id_idx",
            "user_id",
            text("created_at DESC"),
            text("id DESC"),
        ),
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    error: Mapped[str | None] = mapped_column(Text)
    queued_at: Mapped[datetime.datetime] = _timestamptz_default()
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    reserved_units: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    reserved_period_start: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    reserved_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    __table_args__ = (Index("jobs_user_id_idx", "user_id"),)


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="SET NULL")
    )
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = _timestamptz_default()


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(INET)
    at: Mapped[datetime.datetime] = _timestamptz_default()
    meta: Mapped[dict | None] = mapped_column(JSONB)


class RunEvent(Base):
    __tablename__ = "run_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    at: Mapped[datetime.datetime] = _timestamptz_default()

    __table_args__ = (
        UniqueConstraint("run_id", "seq", name="uq_run_events_run_id_seq"),
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    stripe_customer_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(Text, unique=True)
    price_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    current_period_start: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    current_period_end: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime.datetime] = _timestamptz_default()
    updated_at: Mapped[datetime.datetime] = _timestamptz_default()


class UsagePeriod(Base):
    __tablename__ = "usage_periods"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    period_start: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    units_used: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    units_reserved: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "period_start"),
        CheckConstraint("units_used >= 0", name="ck_usage_periods_units_used"),
        CheckConstraint("units_reserved >= 0", name="ck_usage_periods_units_reserved"),
    )


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    period_start: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    kind: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'units'")
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'consumed'")
    )
    created_at: Mapped[datetime.datetime] = _timestamptz_default()

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "period_start",
            "kind",
            "idempotency_key",
            name="uq_usage_events_idempotency",
        ),
        Index("usage_events_user_id_period_start_idx", "user_id", "period_start"),
    )


class LLMUsage(Base):
    __tablename__ = "llm_usage"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    call_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    prompt_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    cost_usd: Mapped[float | None] = mapped_column(Double)
    created_at: Mapped[datetime.datetime] = _timestamptz_default()

    __table_args__ = (
        Index("llm_usage_user_id_created_at_idx", "user_id", "created_at"),
    )


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    provider_event_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    received_at: Mapped[datetime.datetime] = _timestamptz_default()
    processed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'")
    )
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("webhook_events_status_received_at_idx", "status", "received_at"),
    )


class LegalDocument(Base):
    __tablename__ = "legal_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    effective_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("slug", "version", name="uq_legal_documents_slug_version"),
    )


class UserConsent(Base):
    __tablename__ = "user_consents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("legal_documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    accepted_at: Mapped[datetime.datetime] = _timestamptz_default()
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint(
            "user_id", "document_id", name="uq_user_consents_user_document"
        ),
    )
