"""Resolve a user's plan and period balance for the API edge (plan §4).

This is the UX pre-check; ``reserve_units`` remains the authority that bounds
spend.
"""

import datetime
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.billing.plans import Plan, get_plan
from src.billing.units import InsufficientUnits, get_balance, resolve_period
from src.db.models import User


@dataclass(frozen=True)
class Entitlements:
    plan: Plan
    units_used: int
    units_reserved: int
    period_start: datetime.datetime
    period_end: datetime.datetime

    @property
    def units_remaining(self) -> int:
        return max(self.plan.units - self.units_used - self.units_reserved, 0)


async def resolve_entitlements(
    db: AsyncSession, *, user: User, now: datetime.datetime | None = None
) -> Entitlements:
    period_start, period_end = await resolve_period(db, user.id, now)
    units_used, units_reserved = await get_balance(db, user.id, period_start)
    return Entitlements(
        plan=get_plan(user.plan_key),
        units_used=units_used,
        units_reserved=units_reserved,
        period_start=period_start,
        period_end=period_end,
    )


def assert_units_available(entitlements: Entitlements) -> None:
    if entitlements.units_remaining == 0:
        raise InsufficientUnits(entitlements.period_end)
