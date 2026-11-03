"""Stripe access, confined to this module (plan §6).

The ``stripe`` package is imported lazily so booting the API never requires it;
only a real billing call does. Every function returns a plain dict, so handlers
and tests never depend on ``StripeObject``.

Hosted Checkout only: the browser is redirected to Stripe, so there is no
publishable key anywhere — just the secret key and the webhook secret.
"""

from typing import Any

from src.config.settings import get_settings


class BillingNotConfigured(RuntimeError):
    """Billing is switched off or the secret key is missing."""


def billing_configured() -> bool:
    settings = get_settings()
    return bool(settings.billing_enabled and settings.stripe_secret_key)


def get_stripe():
    """The ``stripe`` module with its API key set (lazy import)."""
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise BillingNotConfigured("STRIPE_SECRET_KEY is not set")
    import stripe

    stripe.api_key = settings.stripe_secret_key
    return stripe


def _as_dict(obj: Any) -> dict:
    if isinstance(obj, dict):
        return obj
    return obj.to_dict_recursive()


def retrieve_subscription(subscription_id: str) -> dict:
    return _as_dict(get_stripe().Subscription.retrieve(subscription_id))


def create_customer(*, email: str, user_id: str) -> dict:
    return _as_dict(
        get_stripe().Customer.create(
            email=email, metadata={"user_id": str(user_id)}
        )
    )


def create_checkout_session(
    *,
    customer_id: str,
    price_id: str,
    user_id: str,
    plan: str,
    success_url: str,
    cancel_url: str,
) -> dict:
    return _as_dict(
        get_stripe().checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            client_reference_id=str(user_id),
            metadata={"user_id": str(user_id), "plan": plan},
            subscription_data={
                "metadata": {"user_id": str(user_id), "plan": plan}
            },
            automatic_tax={"enabled": True},
            success_url=success_url,
            cancel_url=cancel_url,
        )
    )


def create_portal_session(*, customer_id: str, return_url: str) -> dict:
    return _as_dict(
        get_stripe().billing_portal.Session.create(
            customer=customer_id, return_url=return_url
        )
    )
