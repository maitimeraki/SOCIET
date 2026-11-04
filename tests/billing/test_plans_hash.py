"""The boot-audit hash: stable across calls, sensitive to any allowance change."""

import pytest

from src.billing.plans import clear_plan_cache, plans_table_hash
from src.config.settings import get_settings


@pytest.fixture(autouse=True)
def _fresh_registry():
    get_settings.cache_clear()
    clear_plan_cache()
    yield
    get_settings.cache_clear()
    clear_plan_cache()


def test_plans_table_hash_is_deterministic():
    assert plans_table_hash() == plans_table_hash()
    assert len(plans_table_hash()) == 64


def test_plans_table_hash_changes_with_a_plan_value(monkeypatch):
    before = plans_table_hash()

    monkeypatch.setenv("PLAN_FREE_UNITS", "2000")
    get_settings.cache_clear()
    clear_plan_cache()

    assert plans_table_hash() != before
