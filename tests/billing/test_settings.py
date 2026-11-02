"""Billing settings: exact defaults and validation, no database needed."""

import pytest

from src.config.settings import Settings


def test_defaults_carry_the_plan_numbers():
    settings = Settings()

    assert settings.billing_enabled is False
    assert settings.legal_contact_email == "hello@societas.app"
    assert (
        settings.plan_free_units,
        settings.plan_starter_units,
        settings.plan_studio_units,
        settings.plan_enterprise_units,
    ) == (1_000, 8_000, 16_000, 80_000)
    assert (
        settings.plan_free_max_agents,
        settings.plan_starter_max_agents,
        settings.plan_studio_max_agents,
        settings.plan_enterprise_max_agents,
    ) == (10, 20, 20, 40)
    assert (
        settings.plan_free_max_rounds,
        settings.plan_starter_max_rounds,
        settings.plan_studio_max_rounds,
        settings.plan_enterprise_max_rounds,
    ) == (3, 4, 4, 4)
    assert settings.unit_tokens == 1_000
    assert settings.chars_per_unit == 2_000
    assert settings.unit_cost_usd == 0.0002
    assert settings.billing_reservation_lease_seconds == 3_600


def test_billing_enabled_requires_stripe_values():
    with pytest.raises(ValueError, match="stripe_secret_key"):
        Settings(billing_enabled=True)

    with pytest.raises(ValueError, match="stripe_price_studio"):
        Settings(
            billing_enabled=True,
            stripe_secret_key="sk_test",
            stripe_webhook_secret="whsec_test",
            stripe_price_starter="price_starter",
        )


def test_billing_enabled_with_all_stripe_values_is_valid():
    settings = Settings(
        billing_enabled=True,
        stripe_secret_key="sk_test",
        stripe_webhook_secret="whsec_test",
        stripe_price_starter="price_starter",
        stripe_price_studio="price_studio",
    )

    assert settings.billing_enabled is True


def test_zero_units_raise():
    for field in ("plan_free_units", "unit_tokens", "chars_per_unit"):
        with pytest.raises(ValueError, match=field):
            Settings(**{field: 0})


def test_odd_or_out_of_range_max_agents_raise():
    with pytest.raises(ValueError, match="plan_free_max_agents"):
        Settings(plan_free_max_agents=11)
    with pytest.raises(ValueError, match="plan_starter_max_agents"):
        Settings(plan_starter_max_agents=102)


def test_out_of_range_max_rounds_raise():
    with pytest.raises(ValueError, match="plan_free_max_rounds"):
        Settings(plan_free_max_rounds=0)
    with pytest.raises(ValueError, match="plan_enterprise_max_rounds"):
        Settings(plan_enterprise_max_rounds=11)


def test_negative_cost_and_lease_raise():
    with pytest.raises(ValueError, match="unit_cost_usd"):
        Settings(unit_cost_usd=-0.01)
    with pytest.raises(ValueError, match="billing_reservation_lease_seconds"):
        Settings(billing_reservation_lease_seconds=0)
