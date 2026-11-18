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
    ) == (10, 12, 12, 12)
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


RAZORPAY_VALUES = {
    "razorpay_key_id": "rzp_test_key",
    "razorpay_key_secret": "secret",
    "razorpay_webhook_secret": "whsec_test",
    "razorpay_plan_starter_inr": "plan_starter_inr",
    "razorpay_plan_starter_usd": "plan_starter_usd",
    "razorpay_plan_studio_inr": "plan_studio_inr",
    "razorpay_plan_studio_usd": "plan_studio_usd",
}


def test_billing_enabled_requires_razorpay_values():
    with pytest.raises(ValueError, match="razorpay_key_id"):
        Settings(billing_enabled=True)

    values = dict(RAZORPAY_VALUES, razorpay_plan_studio_usd=None)
    with pytest.raises(ValueError, match="razorpay_plan_studio_usd"):
        Settings(billing_enabled=True, **values)


def test_billing_enabled_with_all_razorpay_values_is_valid():
    settings = Settings(billing_enabled=True, **RAZORPAY_VALUES)

    assert settings.billing_enabled is True


def test_razorpay_key_mode_follows_the_environment():
    prod = {"env": "prod", "email_api_key": "email_key"}
    with pytest.raises(ValueError, match="rzp_live_"):
        Settings(**prod, razorpay_key_id="rzp_test_key")
    with pytest.raises(ValueError, match="rzp_test_"):
        Settings(env="dev", razorpay_key_id="rzp_live_key")
    assert Settings(**prod, razorpay_key_id="rzp_live_key").env == "prod"


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
