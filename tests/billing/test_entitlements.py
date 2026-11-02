"""Live tests for entitlements derived from the plan and period balance."""

import datetime
import os
import uuid

import pytest
from sqlalchemy import delete, select

from src.billing.entitlements import (
    assert_units_available,
    resolve_entitlements,
)
from src.billing.plans import get_plan
from src.billing.units import (
    InsufficientUnits,
    _calendar_month_bounds,
    reserve_units,
    resolve_period,
    settle_call,
)
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

NOW = datetime.datetime(2026, 11, 15, 12, 0, tzinfo=datetime.UTC)


async def _make_user(factory) -> uuid.UUID:
    async with factory() as db:
        user = User(
            email=f"entitlements-{uuid.uuid4()}@example.com",
            password_hash="$2b$12$entitlements",
        )
        db.add(user)
        await db.flush()
        user_id = user.id
        await db.commit()
    return user_id


async def _load_user(db, user_id: uuid.UUID) -> User:
    return (await db.execute(select(User).where(User.id == user_id))).scalar_one()


async def _cleanup(factory, user_id: uuid.UUID) -> None:
    async with factory() as db:
        await db.execute(delete(UsageEvent).where(UsageEvent.user_id == user_id))
        await db.execute(delete(LLMUsage).where(LLMUsage.user_id == user_id))
        await db.execute(delete(Subscription).where(Subscription.user_id == user_id))
        await db.execute(delete(Job).where(Job.user_id == user_id))
        await db.execute(delete(UsagePeriod).where(UsagePeriod.user_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


@pytest.mark.asyncio
async def test_fresh_user_gets_full_free_balance(session_factory):
    factory = session_factory
    user_id = await _make_user(factory)
    try:
        async with factory() as db:
            user = await _load_user(db, user_id)
            entitlements = await resolve_entitlements(db, user=user, now=NOW)

        plan = get_plan("free")
        assert entitlements.plan.key == "free"
        assert (entitlements.units_used, entitlements.units_reserved) == (0, 0)
        assert entitlements.units_remaining == plan.units
        assert (entitlements.plan.max_agents, entitlements.plan.max_rounds) == (10, 3)
        assert (entitlements.period_start, entitlements.period_end) == (
            _calendar_month_bounds(NOW)
        )
    finally:
        await _cleanup(factory, user_id)


@pytest.mark.asyncio
async def test_settlement_reduces_remaining(session_factory):
    factory = session_factory
    user_id = await _make_user(factory)
    try:
        async with factory() as db:
            period_start, _ = await resolve_period(db, user_id, NOW)
        async with factory() as db:
            await settle_call(
                db,
                user_id=user_id,
                period_start=period_start,
                source="ingest",
                amount=40,
                idempotency_key=f"call-{uuid.uuid4()}",
            )

        async with factory() as db:
            user = await _load_user(db, user_id)
            entitlements = await resolve_entitlements(db, user=user, now=NOW)

        assert entitlements.units_used == 40
        assert entitlements.units_remaining == get_plan("free").units - 40
    finally:
        await _cleanup(factory, user_id)


@pytest.mark.asyncio
async def test_assert_units_available_raises_at_zero(session_factory):
    factory = session_factory
    user_id = await _make_user(factory)
    try:
        plan = get_plan("free")
        async with factory() as db:
            await reserve_units(
                db, user_id=user_id, plan_key="free", estimate=plan.units, now=NOW
            )

        async with factory() as db:
            user = await _load_user(db, user_id)
            entitlements = await resolve_entitlements(db, user=user, now=NOW)

        assert entitlements.units_remaining == 0
        with pytest.raises(InsufficientUnits) as excinfo:
            assert_units_available(entitlements)
        assert excinfo.value.period_end == entitlements.period_end
    finally:
        await _cleanup(factory, user_id)
