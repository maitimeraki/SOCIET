"""Settlement consumes the job's remaining hold, not only the period's."""

import asyncio
import datetime
import os
import sys
import uuid

import pytest
from sqlalchemy import delete

from src.billing.units import get_balance, reserve_units, settle_call
from src.db.models import Job, UsageEvent, UsagePeriod, User

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)
pytestmark = [requires_db, pytest.mark.asyncio]


async def _make_user(factory) -> uuid.UUID:
    async with factory() as db:
        user = User(
            email=f"auth-test-hold-{uuid.uuid4().hex[:10]}@example.com",
            password_hash="not-a-real-hash",
        )
        db.add(user)
        await db.flush()
        user_id = user.id
        await db.commit()
    return user_id


async def _cleanup(factory, user_id: uuid.UUID) -> None:
    async with factory() as db:
        await db.execute(delete(UsageEvent).where(UsageEvent.user_id == user_id))
        await db.execute(delete(Job).where(Job.user_id == user_id))
        await db.execute(delete(UsagePeriod).where(UsagePeriod.user_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


async def test_settlement_decrements_period_and_job_hold_once(session_factory):
    factory = session_factory
    user_id = await _make_user(factory)
    job_id = uuid.uuid4()
    try:
        async with factory() as db:
            reservation = await reserve_units(
                db, user_id=user_id, plan_key="free", estimate=60
            )
            db.add(
                Job(
                    id=job_id,
                    user_id=user_id,
                    kind="debate",
                    status="running",
                    reserved_units=60,
                    reserved_period_start=reservation.period_start,
                    reserved_at=datetime.datetime.now(datetime.UTC),
                )
            )
            await db.commit()

        key = uuid.uuid4().hex
        async with factory() as db:
            first = await settle_call(
                db,
                user_id=user_id,
                period_start=reservation.period_start,
                source="debate",
                amount=10,
                idempotency_key=key,
                job_id=job_id,
            )
        assert first is True

        async with factory() as db:
            job = await db.get(Job, job_id)
            assert job.reserved_units == 50
            assert await get_balance(db, user_id, reservation.period_start) == (10, 50)

        async with factory() as db:
            duplicate = await settle_call(
                db,
                user_id=user_id,
                period_start=reservation.period_start,
                source="debate",
                amount=10,
                idempotency_key=key,
                job_id=job_id,
            )
        assert duplicate is False

        async with factory() as db:
            job = await db.get(Job, job_id)
            assert job.reserved_units == 50
            assert await get_balance(db, user_id, reservation.period_start) == (10, 50)
    finally:
        await _cleanup(factory, user_id)
