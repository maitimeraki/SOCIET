"""The only module that converts tokens to units and moves a balance.

Reservations are a single conditional UPDATE (never read-then-write); a
settlement inserts its event and updates the period in one statement and is
idempotent by key. Units are always derived from measured usage — never from
a client-supplied amount (plan §4, §5, §8; ledger R3, R13, R18, R19).
"""

import datetime
import math
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.billing.plans import get_plan
from src.config.settings import get_settings
from src.db.models import Job, Subscription, UsageEvent, UsagePeriod

SOURCES = frozenset({"ingest", "ontology", "debate", "verdict"})
TERMINAL_JOB_STATUSES = frozenset({"complete", "completed", "failed", "cancelled"})


@dataclass(frozen=True)
class Reservation:
    user_id: uuid.UUID
    period_start: datetime.datetime
    period_end: datetime.datetime
    amount: int
    units_used: int
    units_reserved: int


class InsufficientUnits(Exception):
    def __init__(self, period_end: datetime.datetime):
        self.period_end = period_end
        super().__init__("Insufficient units for the current period")


def _non_negative_int(value: int, name: str) -> int:
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative int")
    return value


def units_for_tokens(prompt_tokens: int, completion_tokens: int) -> int:
    prompt = _non_negative_int(prompt_tokens, "prompt_tokens")
    completion = _non_negative_int(completion_tokens, "completion_tokens")
    return math.ceil((prompt + completion) / get_settings().unit_tokens)


def units_for_chars(chars: int) -> int:
    return math.ceil(_non_negative_int(chars, "chars") / get_settings().chars_per_unit)


def _calendar_month_bounds(
    now: datetime.datetime,
) -> tuple[datetime.datetime, datetime.datetime]:
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.UTC)
    else:
        now = now.astimezone(datetime.UTC)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


async def resolve_period(
    db: AsyncSession,
    user_id: uuid.UUID,
    now: datetime.datetime | None = None,
) -> tuple[datetime.datetime, datetime.datetime]:
    now = now or datetime.datetime.now(datetime.UTC)
    sub = (
        await db.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status.in_(("trialing", "active")),
                Subscription.current_period_start.is_not(None),
                Subscription.current_period_end.is_not(None),
            )
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if sub is not None:
        return sub.current_period_start, sub.current_period_end
    return _calendar_month_bounds(now)


async def ensure_period(
    db: AsyncSession, user_id: uuid.UUID, period_start: datetime.datetime
) -> None:
    await db.execute(
        pg_insert(UsagePeriod)
        .values(user_id=user_id, period_start=period_start)
        .on_conflict_do_nothing(index_elements=["user_id", "period_start"])
    )


async def get_balance(
    db: AsyncSession, user_id: uuid.UUID, period_start: datetime.datetime
) -> tuple[int, int]:
    row = (
        await db.execute(
            select(UsagePeriod.units_used, UsagePeriod.units_reserved).where(
                UsagePeriod.user_id == user_id,
                UsagePeriod.period_start == period_start,
            )
        )
    ).first()
    return (row.units_used, row.units_reserved) if row is not None else (0, 0)


async def reserve_units(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    plan_key: str | None,
    estimate: int,
    now: datetime.datetime | None = None,
) -> Reservation:
    estimate = _non_negative_int(estimate, "estimate")
    plan = get_plan(plan_key)
    period_start, period_end = await resolve_period(db, user_id, now)
    await ensure_period(db, user_id, period_start)

    row = (
        await db.execute(
            update(UsagePeriod)
            .where(
                UsagePeriod.user_id == user_id,
                UsagePeriod.period_start == period_start,
                (plan.units - UsagePeriod.units_used - UsagePeriod.units_reserved)
                >= estimate,
            )
            .values(units_reserved=UsagePeriod.units_reserved + estimate)
            .returning(UsagePeriod.units_used, UsagePeriod.units_reserved)
        )
    ).first()
    if row is None:
        await db.rollback()
        raise InsufficientUnits(period_end)
    await db.commit()
    return Reservation(
        user_id=user_id,
        period_start=period_start,
        period_end=period_end,
        amount=estimate,
        units_used=row.units_used,
        units_reserved=row.units_reserved,
    )


async def settle_call(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    period_start: datetime.datetime,
    source: str,
    amount: int,
    idempotency_key: str,
    reason: str | None = None,
) -> bool:
    if source not in SOURCES:
        raise ValueError(f"source must be one of {sorted(SOURCES)}")
    amount = _non_negative_int(amount, "amount")
    await ensure_period(db, user_id, period_start)

    inserted = (
        pg_insert(UsageEvent)
        .values(
            user_id=user_id,
            period_start=period_start,
            source=source,
            amount=amount,
            idempotency_key=idempotency_key,
            reason=reason,
        )
        .on_conflict_do_nothing(
            index_elements=["user_id", "period_start", "kind", "idempotency_key"]
        )
        .returning(UsageEvent.id)
        .cte("inserted")
    )
    periods = UsagePeriod.__table__
    settle = (
        periods.update()
        .where(
            periods.c.user_id == user_id,
            periods.c.period_start == period_start,
            select(inserted.c.id).exists(),
        )
        .values(
            units_used=periods.c.units_used + amount,
            units_reserved=func.greatest(periods.c.units_reserved - amount, 0),
        )
        .returning(periods.c.user_id)
        .add_cte(inserted)
    )
    # The period row exists (ensure_period), so a row comes back iff the event
    # was newly inserted — a conflict skips the update.
    event_was_new = (await db.execute(settle)).first() is not None
    await db.commit()
    return event_was_new


async def release_reservation(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    period_start: datetime.datetime,
    amount: int,
) -> None:
    amount = _non_negative_int(amount, "amount")
    await db.execute(
        update(UsagePeriod)
        .where(
            UsagePeriod.user_id == user_id,
            UsagePeriod.period_start == period_start,
        )
        .values(units_reserved=func.greatest(UsagePeriod.units_reserved - amount, 0))
    )
    await db.commit()


async def release_job_reservation(db: AsyncSession, job_id: uuid.UUID) -> int:
    job = (
        await db.execute(select(Job).where(Job.id == job_id).with_for_update())
    ).scalar_one_or_none()
    if job is None:
        await db.commit()
        return 0

    released = 0
    if job.reserved_units > 0 and job.reserved_period_start is not None:
        released = job.reserved_units
        await db.execute(
            update(UsagePeriod)
            .where(
                UsagePeriod.user_id == job.user_id,
                UsagePeriod.period_start == job.reserved_period_start,
            )
            .values(
                units_reserved=func.greatest(UsagePeriod.units_reserved - released, 0)
            )
        )
    job.reserved_units = 0
    job.reserved_at = None
    await db.commit()
    return released


async def release_expired_reservations(
    db: AsyncSession,
    *,
    now: datetime.datetime | None = None,
    limit: int = 100,
) -> list[uuid.UUID]:
    now = now or datetime.datetime.now(datetime.UTC)
    cutoff = now - datetime.timedelta(
        seconds=get_settings().billing_reservation_lease_seconds
    )
    jobs = (
        (
            await db.execute(
                select(Job)
                .where(
                    Job.reserved_units > 0,
                    Job.reserved_at.is_not(None),
                    Job.reserved_at <= cutoff,
                )
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    released: list[uuid.UUID] = []
    for job in jobs:
        if job.reserved_period_start is not None:
            await db.execute(
                update(UsagePeriod)
                .where(
                    UsagePeriod.user_id == job.user_id,
                    UsagePeriod.period_start == job.reserved_period_start,
                )
                .values(
                    units_reserved=func.greatest(
                        UsagePeriod.units_reserved - job.reserved_units, 0
                    )
                )
            )
        job.reserved_units = 0
        job.reserved_at = None
        if job.status not in TERMINAL_JOB_STATUSES:
            job.status = "failed"
            job.finished_at = now
            job.error = "reservation lease expired"
        released.append(job.id)
    await db.commit()
    return released


async def void_event(db: AsyncSession, *, event_id: uuid.UUID, reason: str) -> bool:
    event = (
        await db.execute(
            select(UsageEvent).where(UsageEvent.id == event_id).with_for_update()
        )
    ).scalar_one_or_none()
    if event is None or event.status == "void":
        return False

    event.status = "void"
    event.reason = reason
    if event.user_id is not None:
        await db.execute(
            update(UsagePeriod)
            .where(
                UsagePeriod.user_id == event.user_id,
                UsagePeriod.period_start == event.period_start,
            )
            .values(units_used=func.greatest(UsagePeriod.units_used - event.amount, 0))
        )
    await db.commit()
    return True
