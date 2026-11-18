"""Plan registry: defaults, fallbacks, price mapping, read-only mapping."""

import pytest

from src.billing.plans import (
    FREE_PLAN_KEY,
    clear_plan_cache,
    get_plan,
    get_plans,
    plan_for_razorpay_plan,
    plan_price_minor,
)
from src.config.settings import get_settings


@pytest.fixture(autouse=True)
def _fresh_registry():
    """The registry is a cached snapshot of settings; rebuild around each test."""
    get_settings.cache_clear()
    clear_plan_cache()
    yield
    get_settings.cache_clear()
    clear_plan_cache()


def test_default_plan_values():
    plans = get_plans()
    assert (plans["free"].units, plans["free"].max_agents) == (1_000, 10)
    assert plans["free"].max_rounds == 3
    assert (plans["starter"].units, plans["starter"].max_agents) == (8_000, 12)
    assert plans["starter"].max_rounds == 4
    assert (plans["studio"].units, plans["studio"].max_agents) == (16_000, 12)
    assert plans["studio"].max_rounds == 4
    assert (plans["enterprise"].units, plans["enterprise"].max_agents) == (80_000, 12)
    assert plans["enterprise"].max_rounds == 4
    assert plans["free"].razorpay_plan_ids == {}
    assert plans["enterprise"].razorpay_plan_ids == {}
    assert plans["enterprise"].prices == {"INR": None, "USD": None}


def test_unknown_key_falls_back_to_free():
    assert get_plan(None) == get_plan(FREE_PLAN_KEY)
    assert get_plan("nonsense") == get_plan(FREE_PLAN_KEY)


def test_plan_for_razorpay_plan(monkeypatch):
    monkeypatch.setenv("RAZORPAY_PLAN_STARTER_INR", "plan_starter_inr_test")
    monkeypatch.setenv("RAZORPAY_PLAN_STUDIO_USD", "plan_studio_usd_test")
    get_settings.cache_clear()
    clear_plan_cache()

    assert plan_for_razorpay_plan("plan_starter_inr_test").key == "starter"
    assert plan_for_razorpay_plan("plan_studio_usd_test").key == "studio"
    assert plan_for_razorpay_plan("plan_unknown") is None
    assert plan_for_razorpay_plan(None) is None


def test_plan_price_minor_is_in_minor_units():
    plan = get_plan("starter")

    assert plan_price_minor(plan, "INR") == 999 * 100
    assert plan_price_minor(plan, "USD") == 10 * 100
    assert plan_price_minor(get_plan("enterprise"), "INR") == 0


def test_registry_is_read_only():
    with pytest.raises(TypeError):
        get_plans()["free"] = get_plan("starter")
