"""Plan registry — the single mapping from a plan key to its entitlements.

Built once from ``get_settings()`` and exposed read-only. An unknown or missing
key resolves to the most restrictive plan (free); there is no unlimited branch
(plan §4, ledger R13).
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType

from src.config.settings import get_settings

FREE_PLAN_KEY = "free"
SUPPORTED_CURRENCIES: tuple = ("INR", "USD")


@dataclass(frozen=True)
class Plan:
    key: str
    units: int
    max_agents: int
    max_rounds: int
    # Display units: rupees for INR, dollars for USD. None means no public price.
    prices: Mapping[str, int | None]
    razorpay_plan_ids: Mapping[str, str | None]


@lru_cache
def get_plans() -> Mapping[str, Plan]:
    settings = get_settings()
    return MappingProxyType(
        {
            "free": Plan(
                key="free",
                units=settings.plan_free_units,
                max_agents=settings.plan_free_max_agents,
                max_rounds=settings.plan_free_max_rounds,
                prices={"INR": 0, "USD": 0},
                razorpay_plan_ids={},
            ),
            "starter": Plan(
                key="starter",
                units=settings.plan_starter_units,
                max_agents=settings.plan_starter_max_agents,
                max_rounds=settings.plan_starter_max_rounds,
                prices={
                    "INR": settings.plan_starter_price_inr,
                    "USD": settings.plan_starter_price_usd,
                },
                razorpay_plan_ids={
                    "INR": settings.razorpay_plan_starter_inr,
                    "USD": settings.razorpay_plan_starter_usd,
                },
            ),
            "studio": Plan(
                key="studio",
                units=settings.plan_studio_units,
                max_agents=settings.plan_studio_max_agents,
                max_rounds=settings.plan_studio_max_rounds,
                prices={
                    "INR": settings.plan_studio_price_inr,
                    "USD": settings.plan_studio_price_usd,
                },
                razorpay_plan_ids={
                    "INR": settings.razorpay_plan_studio_inr,
                    "USD": settings.razorpay_plan_studio_usd,
                },
            ),
            "enterprise": Plan(
                key="enterprise",
                units=settings.plan_enterprise_units,
                max_agents=settings.plan_enterprise_max_agents,
                max_rounds=settings.plan_enterprise_max_rounds,
                prices={"INR": None, "USD": None},
                razorpay_plan_ids={},
            ),
        }
    )


def get_plan(key: str | None) -> Plan:
    plans = get_plans()
    return plans.get(key or "", plans[FREE_PLAN_KEY])


def plan_for_razorpay_plan(plan_id: str | None) -> Plan | None:
    if not plan_id:
        return None
    for plan in get_plans().values():
        if plan_id in plan.razorpay_plan_ids.values():
            return plan
    return None


def plan_price_minor(plan: Plan, currency: str) -> int:
    """The plan price in minor units (paise, cents); 0 when unpriced."""
    price = plan.prices.get(currency)
    return 0 if price is None else price * 100


def plans_table_hash() -> str:
    """Stable sha256 over the resolved plan table (audit / drift detection)."""
    payload = {
        key: {
            "units": p.units,
            "max_agents": p.max_agents,
            "max_rounds": p.max_rounds,
            "prices": dict(p.prices),
            "razorpay_plan_ids": dict(p.razorpay_plan_ids),
        }
        for key, p in sorted(get_plans().items())
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def clear_plan_cache() -> None:
    get_plans.cache_clear()
