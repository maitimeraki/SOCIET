"""Live roundtrip tests for the billing/compliance schema.

Requires DATABASE_URL and a migrated database (`alembic upgrade head`); the
whole module is skipped without it. No mocks — every assertion reads real
database behavior.
"""

import datetime
import os
import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from src.db.models import (
    Job,
    LegalDocument,
    LLMUsage,
    UsageEvent,
    UsagePeriod,
    User,
    UserConsent,
    WebhookEvent,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)

PERIOD_START = datetime.datetime(2026, 11, 1, tzinfo=datetime.UTC)


def _email() -> str:
    return f"billing-{uuid.uuid4()}@example.com"


async def _add_user(session) -> uuid.UUID:
    user = User(email=_email(), password_hash="$2b$12$billing")
    session.add(user)
    await session.flush()
    user_id = user.id
    await session.commit()
    return user_id


async def _delete_user(factory, user_id: uuid.UUID) -> None:
    async with factory() as db:
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


@pytest.mark.asyncio
async def test_user_defaults(session_factory):
    factory = session_factory
    user_id = None
    try:
        async with factory() as db:
            user_id = await _add_user(db)

        async with factory() as db:
            user = (
                await db.execute(select(User).where(User.id == user_id))
            ).scalar_one()
            assert (user.role, user.plan_key) == ("user", "free")
            assert user.email_verified_at is None
            assert user.age_confirmed_at is None
    finally:
        if user_id is not None:
            await _delete_user(factory, user_id)


@pytest.mark.asyncio
async def test_usage_period_roundtrip(session_factory):
    factory = session_factory
    user_id = None
    try:
        async with factory() as db:
            user_id = await _add_user(db)

        async with factory() as db:
            db.add(
                UsagePeriod(
                    user_id=user_id,
                    period_start=PERIOD_START,
                    units_used=321,
                    units_reserved=45,
                )
            )
            await db.commit()

        async with factory() as db:
            row = (
                await db.execute(
                    select(UsagePeriod).where(
                        UsagePeriod.user_id == user_id,
                        UsagePeriod.period_start == PERIOD_START,
                    )
                )
            ).scalar_one()
            assert (row.units_used, row.units_reserved) == (321, 45)
    finally:
        if user_id is not None:
            await _delete_user(factory, user_id)


@pytest.mark.asyncio
async def test_usage_event_idempotency(session_factory):
    factory = session_factory
    user_id = None
    event_id = None
    key = f"run-{uuid.uuid4()}"
    try:
        async with factory() as db:
            user_id = await _add_user(db)

        async with factory() as db:
            event = UsageEvent(
                user_id=user_id,
                period_start=PERIOD_START,
                source="debate",
                amount=5,
                idempotency_key=key,
                reason="refund",
            )
            db.add(event)
            await db.commit()
            event_id = event.id

        async with factory() as db:
            event = (
                await db.execute(select(UsageEvent).where(UsageEvent.id == event_id))
            ).scalar_one()
            assert (event.amount, event.reason) == (5, "refund")

        async with factory() as db:
            db.add(
                UsageEvent(
                    user_id=user_id,
                    period_start=PERIOD_START,
                    source="debate",
                    amount=5,
                    idempotency_key=key,
                )
            )
            with pytest.raises(IntegrityError):
                await db.commit()
            await db.rollback()
    finally:
        if user_id is not None:
            await _delete_user(factory, user_id)
        if event_id is not None:
            async with factory() as db:
                await db.execute(delete(UsageEvent).where(UsageEvent.id == event_id))
                await db.commit()


@pytest.mark.asyncio
async def test_webhook_event_idempotency(session_factory):
    factory = session_factory
    event_id = f"evt_{uuid.uuid4()}"
    try:
        async with factory() as db:
            db.add(
                WebhookEvent(
                    provider_event_id=event_id,
                    event_type="invoice.paid",
                    payload_hash="a" * 64,
                )
            )
            await db.commit()

        async with factory() as db:
            db.add(
                WebhookEvent(
                    provider_event_id=event_id,
                    event_type="invoice.paid",
                    payload_hash="b" * 64,
                )
            )
            with pytest.raises(IntegrityError):
                await db.commit()
            await db.rollback()
    finally:
        async with factory() as db:
            await db.execute(
                delete(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
            )
            await db.commit()


@pytest.mark.asyncio
async def test_legal_document_and_consent_uniqueness(session_factory):
    factory = session_factory
    user_id = None
    slug = f"terms-{uuid.uuid4()}"
    document_id = None
    try:
        async with factory() as db:
            user_id = await _add_user(db)

        async with factory() as db:
            document = LegalDocument(
                slug=slug,
                version="1.0",
                effective_at=PERIOD_START,
                content_sha256="a" * 64,
                content="terms",
            )
            db.add(document)
            await db.commit()
            document_id = document.id

        async with factory() as db:
            db.add(
                LegalDocument(
                    slug=slug,
                    version="1.0",
                    effective_at=PERIOD_START,
                    content_sha256="b" * 64,
                    content="terms v2",
                )
            )
            with pytest.raises(IntegrityError):
                await db.commit()
            await db.rollback()

        async with factory() as db:
            db.add(UserConsent(user_id=user_id, document_id=document_id))
            await db.commit()

        async with factory() as db:
            db.add(UserConsent(user_id=user_id, document_id=document_id))
            with pytest.raises(IntegrityError):
                await db.commit()
            await db.rollback()
    finally:
        if user_id is not None:
            await _delete_user(factory, user_id)
        if document_id is not None:
            async with factory() as db:
                await db.execute(
                    delete(LegalDocument).where(LegalDocument.id == document_id)
                )
                await db.commit()


@pytest.mark.asyncio
async def test_user_delete_orphans_financial_rows_and_cascades_usage(session_factory):
    factory = session_factory
    user_id = None
    event_id = None
    llm_id = None
    try:
        async with factory() as db:
            user_id = await _add_user(db)

        async with factory() as db:
            db.add(
                UsagePeriod(
                    user_id=user_id,
                    period_start=PERIOD_START,
                    units_used=1,
                    units_reserved=0,
                )
            )
            event = UsageEvent(
                user_id=user_id,
                period_start=PERIOD_START,
                source="verdict",
                amount=1,
                idempotency_key=f"verdict-{uuid.uuid4()}",
            )
            llm = LLMUsage(
                user_id=user_id,
                call_id=f"call-{uuid.uuid4()}",
                source="debate",
            )
            db.add_all([event, llm])
            await db.commit()
            event_id, llm_id = event.id, llm.id

        await _delete_user(factory, user_id)

        async with factory() as db:
            period = (
                await db.execute(
                    select(UsagePeriod).where(UsagePeriod.user_id == user_id)
                )
            ).scalar_one_or_none()
            assert period is None

            event = (
                await db.execute(select(UsageEvent).where(UsageEvent.id == event_id))
            ).scalar_one()
            llm = (
                await db.execute(select(LLMUsage).where(LLMUsage.id == llm_id))
            ).scalar_one()
            assert event.user_id is None
            assert llm.user_id is None
    finally:
        if user_id is not None:
            await _delete_user(factory, user_id)
        async with factory() as db:
            if event_id is not None:
                await db.execute(delete(UsageEvent).where(UsageEvent.id == event_id))
            if llm_id is not None:
                await db.execute(delete(LLMUsage).where(LLMUsage.id == llm_id))
            await db.commit()


@pytest.mark.asyncio
async def test_job_reserved_units_default(session_factory):
    factory = session_factory
    user_id = None
    job_id = uuid.uuid4()
    try:
        async with factory() as db:
            user_id = await _add_user(db)

        async with factory() as db:
            db.add(
                Job(
                    id=job_id,
                    user_id=user_id,
                    kind="debate",
                    status="queued",
                )
            )
            await db.commit()

        async with factory() as db:
            job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one()
            assert job.reserved_units == 0
            assert job.reserved_period_start is None
            assert job.reserved_at is None
    finally:
        if user_id is not None:
            await _delete_user(factory, user_id)
