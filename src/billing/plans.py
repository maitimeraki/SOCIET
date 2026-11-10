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


@dataclass(frozen=True)
class Plan:
    key: str
    units: int
    max_agents: int
    max_rounds: int
    stripe_price_id: str | None = None


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
            ),
            "starter": Plan(
                key="starter",
                units=settings.plan_starter_units,
                max_agents=settings.plan_starter_max_agents,
                max_rounds=settings.plan_starter_max_rounds,
                stripe_price_id=settings.stripe_price_starter,
            ),
            "studio": Plan(
                key="studio",
                units=settings.plan_studio_units,
                max_agents=settings.plan_studio_max_agents,
                max_rounds=settings.plan_studio_max_rounds,
                stripe_price_id=settings.stripe_price_studio,
            ),
            "enterprise": Plan(
                key="enterprise",
                units=settings.plan_enterprise_units,
                max_agents=settings.plan_enterprise_max_agents,
                max_rounds=settings.plan_enterprise_max_rounds,
            ),
        }
    )


def get_plan(key: str | None) -> Plan:
    plans = get_plans()
    return plans.get(key or "", plans[FREE_PLAN_KEY])


def plan_for_price(price_id: str | None) -> Plan | None:
    if not price_id:
        return None
    for plan in get_plans().values():
        if plan.stripe_price_id == price_id:
            return plan
    return None


def plans_table_hash() -> str:
    """Stable sha256 over the resolved plan table (audit / drift detection)."""
    payload = {
        key: {
            "units": p.units,
            "max_agents": p.max_agents,
            "max_rounds": p.max_rounds,
            "price": p.stripe_price_id,
        }
        for key, p in sorted(get_plans().items())
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def clear_plan_cache() -> None:
    get_plans.cache_clear()
