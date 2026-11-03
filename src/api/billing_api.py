"""The one usage read the frontend may render (plan §6, §8).

Units only — never tokens, cost, model, provider or internal plan figures.
"""

import datetime

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.deps import current_user
from src.billing.entitlements import resolve_entitlements
from src.config.settings import get_settings
from src.db.engine import get_db
from src.db.models import User

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


class UsageOut(BaseModel):
    plan: str
    units_total: int
    units_used: int
    units_remaining: int
    period_start: datetime.datetime
    period_end: datetime.datetime
    limits: dict[str, int]
    billing_enabled: bool


@router.get("/usage", response_model=UsageOut)
async def usage(
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> UsageOut:
    entitlements = await resolve_entitlements(db, user=user)
    response.headers["Cache-Control"] = "private, no-store"
    return UsageOut(
        plan=entitlements.plan.key,
        units_total=entitlements.plan.units,
        units_used=entitlements.units_used,
        units_remaining=entitlements.units_remaining,
        period_start=entitlements.period_start,
        period_end=entitlements.period_end,
        limits={
            "max_agents": entitlements.plan.max_agents,
            "max_rounds": entitlements.plan.max_rounds,
        },
        billing_enabled=get_settings().billing_enabled,
    )
