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


async def _make_job(factory, *, user_id, reserved_units, period_start, kind="debate"):
    job_id = uuid.uuid4()
    async with factory() as db:
        db.add(
            Job(
                id=job_id,
                user_id=user_id,
                kind=kind,
                status="running",
                reserved_units=reserved_units,
                reserved_period_start=period_start,
                reserved_at=datetime.datetime.now(datetime.UTC),
            )
        )
        await db.commit()
    return job_id


async def test_settling_above_its_own_hold_leaves_a_siblings_hold_intact(
    session_factory,
):
    """A's settlement consumes A's hold only; B's 60 units stay reserved."""
    factory = session_factory
    user_id = await _make_user(factory)
    try:
        async with factory() as db:
            first = await reserve_units(
                db, user_id=user_id, plan_key="free", estimate=60
            )
            second = await reserve_units(
                db, user_id=user_id, plan_key="free", estimate=60
            )
        job_a = await _make_job(
            factory,
            user_id=user_id,
            reserved_units=60,
            period_start=first.period_start,
        )
        job_b = await _make_job(
            factory,
            user_id=user_id,
            reserved_units=60,
            period_start=second.period_start,
        )

        async with factory() as db:
            settled = await settle_call(
                db,
                user_id=user_id,
                period_start=first.period_start,
                source="debate",
                amount=150,
                idempotency_key=uuid.uuid4().hex,
                job_id=job_a,
            )
        assert settled is True

        async with factory() as db:
            assert (await db.get(Job, job_a)).reserved_units == 0
            assert (await db.get(Job, job_b)).reserved_units == 60
            # used records the full measured amount; only A's 60 was released.
            assert await get_balance(db, user_id, first.period_start) == (150, 60)
    finally:
        await _cleanup(factory, user_id)


async def test_settling_a_job_with_no_remaining_hold_releases_nothing(
    session_factory,
):
    factory = session_factory
    user_id = await _make_user(factory)
    try:
        async with factory() as db:
            reservation = await reserve_units(
                db, user_id=user_id, plan_key="free", estimate=60
            )
        job_id = await _make_job(
            factory,
            user_id=user_id,
            reserved_units=0,
            period_start=reservation.period_start,
        )

        async with factory() as db:
            assert await settle_call(
                db,
                user_id=user_id,
                period_start=reservation.period_start,
                source="debate",
                amount=25,
                idempotency_key=uuid.uuid4().hex,
                job_id=job_id,
            )

        async with factory() as db:
            assert (await db.get(Job, job_id)).reserved_units == 0
            # The sibling's 60-unit hold is untouched.
            assert await get_balance(db, user_id, reservation.period_start) == (25, 60)
    finally:
        await _cleanup(factory, user_id)


async def test_duplicate_settlement_moves_neither_counter(session_factory):
    factory = session_factory
    user_id = await _make_user(factory)
    try:
        async with factory() as db:
            reservation = await reserve_units(
                db, user_id=user_id, plan_key="free", estimate=60
            )
        job_id = await _make_job(
            factory,
            user_id=user_id,
            reserved_units=60,
            period_start=reservation.period_start,
        )
        key = uuid.uuid4().hex
        for _ in range(2):
            async with factory() as db:
                await settle_call(
                    db,
                    user_id=user_id,
                    period_start=reservation.period_start,
                    source="debate",
                    amount=10,
                    idempotency_key=key,
                    job_id=job_id,
                )

        async with factory() as db:
            assert (await db.get(Job, job_id)).reserved_units == 50
            assert await get_balance(db, user_id, reservation.period_start) == (10, 50)
    finally:
        await _cleanup(factory, user_id)


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
