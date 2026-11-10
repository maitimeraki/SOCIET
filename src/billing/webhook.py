"""Stripe webhook verification, idempotent storage and the event state machine.

The event payload is never the source of entitlement: every subscription event
triggers a fresh retrieve from Stripe, and the plan is derived from that
object. The local ``subscriptions`` row is the mirror; ``users.plan_key`` is
written only here (and by admin actions), never from a request body.
"""

import datetime
import json
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.audit import record as audit_record
from src.billing import stripe_client
from src.billing.plans import plan_for_price
from src.db.models import Subscription, User, WebhookEvent

_GRANTED_STATUSES = frozenset({"trialing", "active"})
_REVOKED_STATUSES = frozenset({"canceled", "unpaid", "incomplete_expired"})


def verify_signature(
    raw_body: bytes, header: str | None, *, secret: str, tolerance: int
) -> None:
    """Verify ``Stripe-Signature`` against the raw body (constant-time, the
    Stripe library's own implementation). Raises on any mismatch."""
    import stripe

    stripe.WebhookSignature.verify_header(raw_body, header, secret, tolerance)


def parse_event(raw_body: bytes) -> dict:
    return json.loads(raw_body)


async def store_event(db: AsyncSession, event: dict, payload_hash: str) -> bool:
    """Insert the event, or do nothing if the id was already recorded.

    Returns True iff this call inserted the row — the caller enqueues processing
    only for the first delivery.
    """
    inserted = (
        await db.execute(
            pg_insert(WebhookEvent)
            .values(
                provider_event_id=event["id"],
                event_type=event["type"],
                payload_hash=payload_hash,
                payload=event,
            )
            .on_conflict_do_nothing(index_elements=["provider_event_id"])
            .returning(WebhookEvent.id)
        )
    ).scalar_one_or_none()
    await db.commit()
    return inserted is not None


async def handle_event(db: AsyncSession, event: dict) -> None:
    """Apply one verified event. Unknown and record-only types are a no-op."""
    event_type = event.get("type")
    obj = (event.get("data") or {}).get("object") or {}
    event_id = event["id"]

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(db, obj, triggering_event_id=event_id)
    elif event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        if obj.get("id"):
            await _sync_subscription(
                db,
                stripe_client.retrieve_subscription(obj["id"]),
                triggering_event_id=event_id,
            )
    elif event_type in (
        "invoice.paid",
        "invoice.payment_failed",
        "invoice.finalization_failed",
    ):
        # API 2025-03-31 (Basil) moved this under parent.subscription_details.
        subscription_id = obj.get("subscription") or (
            (obj.get("parent") or {}).get("subscription_details") or {}
        ).get("subscription")
        if subscription_id:
            await _sync_subscription(
                db,
                stripe_client.retrieve_subscription(subscription_id),
                triggering_event_id=event_id,
            )
    # customer.updated, charge.refunded, charge.dispute.created,
    # radar.early_fraud_warning.created and unknown types: recorded only.


async def _find_mirror(
    db: AsyncSession,
    *,
    subscription_id: str | None = None,
    customer_id: str | None = None,
    user_id: uuid.UUID | None = None,
) -> Subscription | None:
    if subscription_id:
        row = (
            await db.execute(
                select(Subscription).where(
                    Subscription.stripe_subscription_id == subscription_id
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            return row
    if customer_id:
        row = (
            await db.execute(
                select(Subscription)
                .where(Subscription.stripe_customer_id == customer_id)
                .order_by(Subscription.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is not None:
            return row
    if user_id:
        return (
            await db.execute(
                select(Subscription)
                .where(Subscription.user_id == user_id)
                .order_by(Subscription.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    return None


def _as_uuid(value: object) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


async def _handle_checkout_completed(
    db: AsyncSession, session_obj: dict, *, triggering_event_id: str
) -> None:
    """Reuse (or create) the mirror for this customer, then sync the subscription."""
    user_id = _as_uuid(
        session_obj.get("client_reference_id")
        or (session_obj.get("metadata") or {}).get("user_id")
    )
    customer_id = session_obj.get("customer")

    row = await _find_mirror(db, customer_id=customer_id, user_id=user_id)
    if row is None:
        if user_id is None or not customer_id:
            raise ValueError("unmapped checkout session")
        row = Subscription(
            user_id=user_id, stripe_customer_id=customer_id, status="incomplete"
        )
        db.add(row)
        await db.commit()
    elif customer_id and row.stripe_customer_id != customer_id:
        row.stripe_customer_id = customer_id
        await db.commit()

    subscription_id = session_obj.get("subscription")
    if subscription_id:
        await _sync_subscription(
            db,
            stripe_client.retrieve_subscription(subscription_id),
            triggering_event_id=triggering_event_id,
        )


def _unix(value: object) -> datetime.datetime | None:
    if value is None:
        return None
    return datetime.datetime.fromtimestamp(int(value), tz=datetime.UTC)


async def _sync_subscription(
    db: AsyncSession, sub: dict, *, triggering_event_id: str
) -> None:
    """Mirror one retrieved Stripe subscription and apply its plan transition."""
    subscription_id = sub.get("id")
    customer_id = sub.get("customer")
    items = (sub.get("items") or {}).get("data") or []
    first_item = items[0] if items else {}
    price_id = (first_item.get("price") or {}).get("id")
    # API 2025-03-31 (Basil) moved the period onto the subscription item.
    period_start = sub.get("current_period_start") or first_item.get(
        "current_period_start"
    )
    period_end = sub.get("current_period_end") or first_item.get(
        "current_period_end"
    )

    row = await _find_mirror(
        db, subscription_id=subscription_id, customer_id=customer_id
    )
    if row is None:
        raise ValueError("unmapped subscription")

    row.stripe_subscription_id = subscription_id
    row.stripe_customer_id = customer_id
    row.status = sub.get("status")
    row.price_id = price_id
    row.current_period_start = _unix(period_start)
    row.current_period_end = _unix(period_end)
    row.cancel_at_period_end = bool(sub.get("cancel_at_period_end"))
    row.updated_at = datetime.datetime.now(datetime.UTC)
    await db.commit()

    if row.user_id is None:
        return
    user = await db.get(User, row.user_id)
    if user is None:
        return

    status = sub.get("status")
    if status in _GRANTED_STATUSES:
        plan = plan_for_price(price_id)
        new_key = plan.key if plan is not None else "free"
    elif status in _REVOKED_STATUSES:
        new_key = "free"
    else:
        # past_due / incomplete / paused: leave the plan exactly as it was.
        return

    if new_key != user.plan_key:
        previous = user.plan_key
        user.plan_key = new_key
        await db.commit()
        await audit_record(
            db,
            "plan_change",
            user_id=user.id,
            meta={
                "from": previous,
                "to": new_key,
                "actor": "stripe",
                "stripe_event_id": triggering_event_id,
            },
        )
