"""Razorpay access, confined to this module (plan §6).

The ``razorpay`` package is imported lazily so booting the API never requires it;
only a real billing call does. Every function returns a plain dict.

Subscriptions only: the browser is sent to Razorpay's hosted checkout, so the key
secret stays server-side and the webhook secret verifies callbacks.
"""

import time
from typing import Any

from src.config.settings import get_settings


class BillingNotConfigured(RuntimeError):
    """Billing is switched off or the Razorpay key pair is missing."""


#: Every Razorpay request is bounded per attempt so a slow provider cannot pin a
#: worker thread. Retries stay off (the SDK default): a retried POST could create
#: a second subscription.
TIMEOUT_SECONDS = 15

#: An unauthorised subscription expires after this window, so an abandoned checkout
#: moves to "expired" (not blocking) instead of blocking the user forever.
AUTHORISATION_WINDOW_SECONDS = 3600


def __getattr__(name: str) -> Any:
    # Lazy: the SDK's exception classes exist only when the package is installed.
    if name == "PROVIDER_ERRORS":
        import requests
        from razorpay.errors import BadRequestError, GatewayError, ServerError

        return (BadRequestError, GatewayError, ServerError, requests.RequestException)
    raise AttributeError(name)


def billing_configured() -> bool:
    settings = get_settings()
    return bool(
        settings.billing_enabled
        and settings.razorpay_key_id
        and settings.razorpay_key_secret
    )


def get_client():
    settings = get_settings()
    if not (settings.razorpay_key_id and settings.razorpay_key_secret):
        raise BillingNotConfigured("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are not set")
    import razorpay

    return razorpay.Client(
        auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
    )


def create_subscription(
    *,
    plan_id: str,
    user_id: str,
    plan_key: str,
    currency: str,
    country: str,
    total_count: int,
) -> dict:
    return get_client().subscription.create(
        {
            "plan_id": plan_id,
            "total_count": total_count,
            "expire_by": int(time.time()) + AUTHORISATION_WINDOW_SECONDS,
            "customer_notify": 1,
            "notes": {
                "user_id": user_id,
                "plan": plan_key,
                "currency": currency,
                "country": country,
            },
        },
        timeout=TIMEOUT_SECONDS,
    )


def retrieve_subscription(subscription_id: str) -> dict:
    return get_client().subscription.fetch(subscription_id, timeout=TIMEOUT_SECONDS)


def cancel_subscription(subscription_id: str, *, at_cycle_end: bool) -> dict:
    return get_client().subscription.cancel(
        subscription_id,
        {"cancel_at_cycle_end": 1 if at_cycle_end else 0},
        timeout=TIMEOUT_SECONDS,
    )


def verify_webhook_signature(raw_body: bytes, signature: str | None, *, secret: str) -> None:
    """Raises ``razorpay.errors.SignatureVerificationError`` on mismatch."""
    if not signature:
        raise ValueError("missing X-Razorpay-Signature")
    import razorpay

    razorpay.Client().utility.verify_webhook_signature(
        raw_body.decode("utf-8"), signature, secret
    )
