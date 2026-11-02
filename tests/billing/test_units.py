"""Live tests for the atomic unit ledger — no mocks, real Postgres behavior."""

import asyncio
import datetime
import os
import uuid

import pytest
from sqlalchemy import delete, select, update

from src.billing.plans import get_plan
from src.billing.units import (
    InsufficientUnits,
    Reservation,
    _calendar_month_bounds,
    ensure_period,
    get_balance,
    release_expired_reservations,
    release_reservation,
    reserve_units,
    resolve_period,
    settle_call,
    units_for_chars,
    units_for_tokens,
    void_event,
)
from src.config.settings import get_settings
from src.db.models import (
    Job,
    LLMUsage,
    Subscription,
    UsageEvent,
    UsagePeriod,
    User,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)


async def _make_user(factory) -> uuid.UUID:
    async with factory() as db:
        user = User(
            email=f"units-{uuid.uuid4()}@example.com", password_hash="$2b$12$units"
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


async def _period_bounds(factory, user_id: uuid.UUID):
    async with factory() as db:
        return await resolve_period(db, user_id)


async def _set_reserved(factory, user_id: uuid.UUID, period_start, amount: int) -> None:
    await _set_units(factory, user_id, period_start, units_reserved=amount)


async def _set_units(factory, user_id: uuid.UUID, period_start, **values: int) -> None:
    async with factory() as db:
        await ensure_period(db, user_id, period_start)
        await db.execute(
            update(UsagePeriod)
            .where(
                UsagePeriod.user_id == user_id,
                UsagePeriod.period_start == period_start,
            )
            .values(**values)
        )
        await db.commit()


def test_units_for_tokens_rounds_up():
    assert units_for_tokens(0, 0) == 0
    assert units_for_tokens(1, 0) == 1
    assert units_for_tokens(1_000, 0) == 1
    assert units_for_tokens(1_000, 1) == 2
    assert units_for_tokens(2_500, 2_500) == 5


def test_units_for_tokens_rejects_negative():
    with pytest.raises(ValueError):
        units_for_tokens(-1, 0)
    with pytest.raises(ValueError):
        units_for_tokens(0, -1)
    with pytest.raises(ValueError):
        units_for_tokens(1.5, 0)


def test_units_for_chars():
    assert units_for_chars(0) == 0
    assert units_for_chars(2_000) == 1
    assert units_for_chars(2_001) == 2
    with pytest.raises(ValueError):
        units_for_chars(-1)


@pytest.mark.asyncio
async def test_reserve_within_limit_and_beyond(session_factory):
    factory = session_factory
    user_id = await _make_user(factory)
    try:
        period_start, period_end = await _period_bounds(factory, user_id)
        async with factory() as db:
            reservation = await reserve_units(
                db, user_id=user_id, plan_key="free", estimate=100
            )
        assert isinstance(reservation, Reservation)
        assert (reservation.amount, reservation.units_used) == (100, 0)
        assert reservation.units_reserved == 100
        assert (reservation.period_start, reservation.period_end) == (
            period_start,
            period_end,
        )

        async with factory() as db:
            assert await get_balance(db, user_id, period_start) == (0, 100)

        plan = get_plan("free")
        async with factory() as db:
            with pytest.raises(InsufficientUnits) as excinfo:
                await reserve_units(
                    db, user_id=user_id, plan_key="free", estimate=plan.units
                )
        assert excinfo.value.period_end == period_end

        async with factory() as db:
            assert await get_balance(db, user_id, period_start) == (0, 100)
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
async def test_concurrent_reservations_admit_exactly_one(session_factory):
    factory = session_factory
    user_id = await _make_user(factory)
    try:
        plan = get_plan("free")
        period_start, _ = await _period_bounds(factory, user_id)
        # Leave exactly 100 units of headroom: two 60-unit reserves cannot both fit.
        await _set_units(factory, user_id, period_start, units_used=plan.units - 100)

        results = await asyncio.gather(
            _reserve_concurrently(factory, user_id, 60),
            _reserve_concurrently(factory, user_id, 60),
        )
        winners = [r for r in results if isinstance(r, Reservation)]
        losers = [r for r in results if isinstance(r, InsufficientUnits)]
        assert len(winners) == 1
        assert len(losers) == 1

        async with factory() as db:
            assert await get_balance(db, user_id, period_start) == (
                plan.units - 100,
                60,
            )
    finally:
        await _cleanup(factory, user_id)


@pytest.mark.asyncio
async def test_settle_call_is_idempotent(session_factory):
    factory = session_factory
    user_id = await _make_user(factory)
    try:
        period_start, _ = await _period_bounds(factory, user_id)
        await _set_reserved(factory, user_id, period_start, 100)
        key = f"call-{uuid.uuid4()}"

        async with factory() as db:
            first = await settle_call(
                db,
                user_id=user_id,
                period_start=period_start,
                source="debate",
                amount=40,
                idempotency_key=key,
            )
        async with factory() as db:
            second = await settle_call(
                db,
                user_id=user_id,
                period_start=period_start,
                source="debate",
                amount=40,
                idempotency_key=key,
            )
        assert first is True
        assert second is False

        async with factory() as db:
            assert await get_balance(db, user_id, period_start) == (40, 60)
            events = (
                (
                    await db.execute(
                        select(UsageEvent).where(
                            UsageEvent.user_id == user_id,
                            UsageEvent.idempotency_key == key,
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(events) == 1

        with pytest.raises(ValueError):
            async with factory() as db:
                await settle_call(
                    db,
                    user_id=user_id,
                    period_start=period_start,
                    source="bogus",
                    amount=1,
                    idempotency_key=f"call-{uuid.uuid4()}",
                )
    finally:
        await _cleanup(factory, user_id)


@pytest.mark.asyncio
async def test_release_reservation_clamps_at_zero(session_factory):
    factory = session_factory
    user_id = await _make_user(factory)
    try:
        period_start, _ = await _period_bounds(factory, user_id)
        await _set_reserved(factory, user_id, period_start, 10)

        async with factory() as db:
            await release_reservation(
                db, user_id=user_id, period_start=period_start, amount=50
            )

        async with factory() as db:
            assert await get_balance(db, user_id, period_start) == (0, 0)
    finally:
        await _cleanup(factory, user_id)


@pytest.mark.asyncio
async def test_release_expired_reservations(session_factory):
    factory = session_factory
    user_id = await _make_user(factory)
    try:
        period_start, _ = await _period_bounds(factory, user_id)
        now = datetime.datetime.now(datetime.UTC)
        stale = now - datetime.timedelta(
            seconds=get_settings().billing_reservation_lease_seconds + 60
        )

        queued_id = uuid.uuid4()
        failed_id = uuid.uuid4()
        fresh_id = uuid.uuid4()
        async with factory() as db:
            await ensure_period(db, user_id, period_start)
            await db.execute(
                update(UsagePeriod)
                .where(
                    UsagePeriod.user_id == user_id,
                    UsagePeriod.period_start == period_start,
                )
                .values(units_reserved=30)
            )
            db.add_all(
                [
                    Job(
                        id=queued_id,
                        user_id=user_id,
                        kind="debate",
                        status="queued",
                        reserved_units=10,
                        reserved_period_start=period_start,
                        reserved_at=stale,
                    ),
                    Job(
                        id=failed_id,
                        user_id=user_id,
                        kind="debate",
                        status="failed",
                        reserved_units=10,
                        reserved_period_start=period_start,
                        reserved_at=stale,
                    ),
                    Job(
                        id=fresh_id,
                        user_id=user_id,
                        kind="debate",
                        status="queued",
                        reserved_units=10,
                        reserved_period_start=period_start,
                        reserved_at=now,
                    ),
                ]
            )
            await db.commit()

        async with factory() as db:
            released = await release_expired_reservations(db, now=now)

        assert set(released) == {queued_id, failed_id}
        assert fresh_id not in released

        async with factory() as db:
            queued = (
                await db.execute(select(Job).where(Job.id == queued_id))
            ).scalar_one()
            failed = (
                await db.execute(select(Job).where(Job.id == failed_id))
            ).scalar_one()
            fresh = (
                await db.execute(select(Job).where(Job.id == fresh_id))
            ).scalar_one()
            assert queued.status == "failed"
            assert queued.error == "reservation lease expired"
            assert queued.finished_at == now
            assert (queued.reserved_units, queued.reserved_at) == (0, None)
            assert failed.status == "failed"
            assert (failed.reserved_units, failed.reserved_at) == (0, None)
            assert fresh.status == "queued"
            assert fresh.reserved_units == 10
            assert fresh.reserved_at == now
            assert await get_balance(db, user_id, period_start) == (0, 10)
    finally:
        await _cleanup(factory, user_id)


@pytest.mark.asyncio
async def test_void_event_restores_units_once(session_factory):
    factory = session_factory
    user_id = await _make_user(factory)
    try:
        period_start, _ = await _period_bounds(factory, user_id)
        await _set_reserved(factory, user_id, period_start, 100)
        key = f"call-{uuid.uuid4()}"
        async with factory() as db:
            await settle_call(
                db,
                user_id=user_id,
                period_start=period_start,
                source="debate",
                amount=40,
                idempotency_key=key,
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
                await void_event(db, event_id=event_id, reason="provider error") is True
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
            assert (event.status, event.reason) == ("void", "provider error")
            assert await get_balance(db, user_id, period_start) == (0, 60)
    finally:
        await _cleanup(factory, user_id)


@pytest.mark.asyncio
async def test_resolve_period_prefers_active_subscription(session_factory):
    factory = session_factory
    user_id = await _make_user(factory)
    try:
        now = datetime.datetime(2026, 11, 15, 9, 30, tzinfo=datetime.UTC)
        calendar = _calendar_month_bounds(now)
        async with factory() as db:
            assert await resolve_period(db, user_id, now) == calendar

        sub_start = datetime.datetime(2026, 10, 9, tzinfo=datetime.UTC)
        sub_end = datetime.datetime(2026, 11, 9, tzinfo=datetime.UTC)
        async with factory() as db:
            db.add(
                Subscription(
                    user_id=user_id,
                    stripe_customer_id=f"cus_{uuid.uuid4()}",
                    price_id="price_test",
                    status="trialing",
                    current_period_start=sub_start,
                    current_period_end=sub_end,
                )
            )
            await db.commit()

        async with factory() as db:
            assert await resolve_period(db, user_id, now) == (sub_start, sub_end)
    finally:
        await _cleanup(factory, user_id)
