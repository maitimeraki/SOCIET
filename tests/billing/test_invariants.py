"""Task 15: ledger invariants, live against Postgres (plan §4, R12, R27).

The identity under test::

    usage_periods.units_used == SUM(usage_events.amount WHERE status='consumed')

and the surrounding rules — idempotent retries count once, a void subtracts
once and keeps the row, two concurrent reservations cannot oversubscribe the
plan, and periods never leak into each other. Ingest and debate draw from the
one pool (plan §4), so the last test proves a hold on one is visible to the
other.
"""

import asyncio
import datetime
import os
import sys
import uuid

import pytest
from sqlalchemy import delete, func, select, update

from src.billing.plans import get_plan
from src.billing.units import (
    InsufficientUnits,
    Reservation,
    _calendar_month_bounds,
    ensure_period,
    get_balance,
    release_job_reservation,
    release_reservation,
    reserve_units,
    resolve_period,
    settle_call,
    void_event,
)
from src.db.models import (
    Job,
    LLMUsage,
    Subscription,
    UsageEvent,
    UsagePeriod,
    User,
)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)


async def _make_user(factory) -> uuid.UUID:
    async with factory() as db:
        user = User(
            email=f"invariant-{uuid.uuid4()}@example.com",
            password_hash="$2b$12$invariants",
        )
        db.add(user)
        await db.flush()
        user_id = user.id
        await db.commit()
    return user_id


async def _cleanup(factory, user_id: uuid.UUID) -> None:
    async with factory() as db:
        await db.execute(delete(UsageEvent).where(UsageEvent.user_id == user_id))
        await db.execute(delete(LLMUsage).where(LLMUsage.user_id == user_id))
        await db.execute(delete(Subscription).where(Subscription.user_id == user_id))
        await db.execute(delete(Job).where(Job.user_id == user_id))
        await db.execute(delete(UsagePeriod).where(UsagePeriod.user_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


async def _period(factory, user_id: uuid.UUID):
    async with factory() as db:
        return await resolve_period(db, user_id)


async def _consumed_sum(factory, user_id: uuid.UUID, period_start) -> int:
    async with factory() as db:
        total = (
            await db.execute(
                select(func.coalesce(func.sum(UsageEvent.amount), 0)).where(
                    UsageEvent.user_id == user_id,
                    UsageEvent.period_start == period_start,
                    UsageEvent.status == "consumed",
                )
            )
        ).scalar_one()
    return int(total)


async def _assert_identity(factory, user_id: uuid.UUID, period_start):
    async with factory() as db:
        used, reserved = await get_balance(db, user_id, period_start)
    assert used == await _consumed_sum(factory, user_id, period_start)
    return used, reserved


async def _settle(factory, user_id, period_start, *, amount, key=None, **kwargs):
    key = key or f"call-{uuid.uuid4()}"
    async with factory() as db:
        return await settle_call(
            db,
            user_id=user_id,
            period_start=period_start,
            amount=amount,
            idempotency_key=key,
            **kwargs,
        )


@pytest.mark.asyncio
async def test_ledger_identity_holds_across_reserve_settle_and_release(session_factory):
    factory = session_factory
    user_id = await _make_user(factory)
    job_id = uuid.uuid4()
    try:
        period_start, _ = await _period(factory, user_id)
        async with factory() as db:
            reservation = await reserve_units(
                db, user_id=user_id, plan_key="free", estimate=100
            )
            db.add(
                Job(
                    id=job_id,
                    user_id=user_id,
                    kind="debate",
                    status="running",
                    reserved_units=100,
                    reserved_period_start=reservation.period_start,
                    reserved_at=datetime.datetime.now(datetime.UTC),
                )
            )
            await db.commit()

        for amount in (10, 20, 30):
            assert await _settle(
                factory,
                user_id,
                period_start,
                amount=amount,
                source="debate",
                job_id=job_id,
            )

        async with factory() as db:
            job = await db.get(Job, job_id)
            assert job.reserved_units == 40  # the remaining hold (R27)

        async with factory() as db:
            released = await release_job_reservation(db, job_id)
        assert released == 40

        used, reserved = await _assert_identity(factory, user_id, period_start)
        assert (used, reserved) == (60, 0)
        assert await _consumed_sum(factory, user_id, period_start) == 60

        async with factory() as db:
            job = await db.get(Job, job_id)
            assert (job.reserved_units, job.reserved_at) == (0, None)
    finally:
        await _cleanup(factory, user_id)


@pytest.mark.asyncio
async def test_retry_of_one_idempotency_key_counts_once(session_factory):
    factory = session_factory
    user_id = await _make_user(factory)
    try:
        period_start, _ = await _period(factory, user_id)
        key = f"call-{uuid.uuid4()}"

        first = await _settle(
            factory, user_id, period_start, amount=40, key=key, source="debate"
        )
        second = await _settle(
            factory, user_id, period_start, amount=40, key=key, source="debate"
        )

        assert (first, second) == (True, False)
        used, reserved = await _assert_identity(factory, user_id, period_start)
        assert used == 40
        assert await _consumed_sum(factory, user_id, period_start) == 40
    finally:
        await _cleanup(factory, user_id)


@pytest.mark.asyncio
async def test_void_subtracts_once_and_keeps_the_event(session_factory):
    factory = session_factory
    user_id = await _make_user(factory)
    try:
        period_start, _ = await _period(factory, user_id)
        key = f"call-{uuid.uuid4()}"
        await _settle(
            factory, user_id, period_start, amount=40, key=key, source="debate"
        )
        async with factory() as db:
            event_id = (
                await db.execute(
                    select(UsageEvent.id).where(
                        UsageEvent.user_id == user_id,
                        UsageEvent.idempotency_key == key,
                    )
                )
            ).scalar_one()

        async with factory() as db:
            assert (
                await void_event(db, event_id=event_id, reason="provider error")
                is True
            )
        async with factory() as db:
            assert (
                await void_event(db, event_id=event_id, reason="provider error")
                is False
            )

        async with factory() as db:
            event = (
                await db.execute(select(UsageEvent).where(UsageEvent.id == event_id))
            ).scalar_one()
            assert (event.status, event.reason, event.amount) == (
                "void",
                "provider error",
                40,
            )

        used, _ = await _assert_identity(factory, user_id, period_start)
        assert used == 0
        assert await _consumed_sum(factory, user_id, period_start) == 0
    finally:
        await _cleanup(factory, user_id)


async def _reserve_concurrently(factory, user_id, estimate):
    async with factory() as db:
        try:
            return await reserve_units(
                db, user_id=user_id, plan_key="free", estimate=estimate
            )
        except InsufficientUnits as exc:
            return exc


@pytest.mark.asyncio
async def test_concurrent_reservations_never_exceed_the_plan_total(session_factory):
    factory = session_factory
    user_id = await _make_user(factory)
    try:
        plan = get_plan("free")
        period_start, _ = await _period(factory, user_id)
        # Exactly 100 units of headroom: two 60-unit holds cannot both fit.
        async with factory() as db:
            await ensure_period(db, user_id, period_start)
            await db.execute(
                update(UsagePeriod)
                .where(
                    UsagePeriod.user_id == user_id,
                    UsagePeriod.period_start == period_start,
                )
                .values(units_used=plan.units - 100)
            )
            await db.commit()

        results = await asyncio.gather(
            _reserve_concurrently(factory, user_id, 60),
            _reserve_concurrently(factory, user_id, 60),
        )
        winners = [result for result in results if isinstance(result, Reservation)]
        losers = [result for result in results if isinstance(result, InsufficientUnits)]
        assert (len(winners), len(losers)) == (1, 1)

        # This test seeds `units_used` directly, so only the balance is asserted
        # here — the identity is exercised by the tests that settle events.
        async with factory() as db:
            used, reserved = await get_balance(db, user_id, period_start)
        assert (used, reserved) == (plan.units - 100, 60)
        assert used + reserved <= plan.units
    finally:
        await _cleanup(factory, user_id)


@pytest.mark.asyncio
async def test_periods_are_isolated(session_factory):
    factory = session_factory
    user_id = await _make_user(factory)
    try:
        current_start, _ = await _period(factory, user_id)
        earlier_start = _calendar_month_bounds(
            datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=40)
        )[0]
        assert earlier_start != current_start

        await _settle(
            factory, user_id, earlier_start, amount=25, source="ingest"
        )
        async with factory() as db:
            assert await get_balance(db, user_id, earlier_start) == (25, 0)
            assert await get_balance(db, user_id, current_start) == (0, 0)

        await _settle(
            factory, user_id, current_start, amount=10, source="debate"
        )

        used_earlier, reserved_earlier = await _assert_identity(
            factory, user_id, earlier_start
        )
        used_current, reserved_current = await _assert_identity(
            factory, user_id, current_start
        )
        assert (used_earlier, reserved_earlier) == (25, 0)
        assert (used_current, reserved_current) == (10, 0)
    finally:
        await _cleanup(factory, user_id)


@pytest.mark.asyncio
async def test_ingest_and_debate_share_one_unit_pool(session_factory):
    factory = session_factory
    user_id = await _make_user(factory)
    try:
        plan = get_plan("free")
        period_start, _ = await _period(factory, user_id)

        async with factory() as db:
            ingest_hold = await reserve_units(
                db, user_id=user_id, plan_key="free", estimate=10
            )
        assert ingest_hold.amount == 10

        # The ingest hold is visible to the debate reservation: the pool is
        # shared, not two independent allowances.
        async with factory() as db:
            with pytest.raises(InsufficientUnits):
                await reserve_units(
                    db, user_id=user_id, plan_key="free", estimate=plan.units - 5
                )

        async with factory() as db:
            debate_hold = await reserve_units(
                db, user_id=user_id, plan_key="free", estimate=20
            )
        assert debate_hold.amount == 20

        await _settle(factory, user_id, period_start, amount=5, source="ingest")
        await _settle(factory, user_id, period_start, amount=15, source="debate")

        # These settlements carry no job id, so they record usage without
        # releasing a hold (C1); the caller releases each job's full hold.
        async with factory() as db:
            await release_reservation(
                db,
                user_id=user_id,
                period_start=period_start,
                amount=ingest_hold.amount,
            )
            await release_reservation(
                db,
                user_id=user_id,
                period_start=period_start,
                amount=debate_hold.amount,
            )

        used, reserved = await _assert_identity(factory, user_id, period_start)
        assert (used, reserved) == (20, 0)
        assert plan.units - used - reserved == plan.units - 20
    finally:
        await _cleanup(factory, user_id)
