"""Razorpay webhook: idempotent storage and the subscription state machine.

The event payload is never the source of entitlement: every subscription event
triggers a fresh fetch from Razorpay, and the plan is derived from that object.
The local ``subscriptions`` row is the mirror; ``users.plan_key`` is written only
here (and by admin actions), never from a request body.
"""

import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.audit import record as audit_record
from src.billing import razorpay_client
from src.billing.plans import plan_for_razorpay_plan, plan_price_minor
from src.billing.tax import tax_amount_minor
from src.db.models import Subscription, User, WebhookEvent

#: The remote subscription still exists; cancel and account deletion act on it.
OPEN_SUBSCRIPTION_STATUSES = frozenset(
    {"created", "authenticated", "active", "pending", "paused", "halted"}
)
#: Checkout refuses a second subscription while one of these is live.
BLOCKING_SUBSCRIPTION_STATUSES = frozenset(
    {"created", "authenticated", "active", "pending", "paused"}
)
_GRANTED_STATUSES = frozenset({"active"})
_REVOKED_STATUSES = frozenset({"cancelled", "completed", "expired", "halted"})

_SUBSCRIPTION_EVENTS = frozenset(
    {
        "subscription.authenticated",
        "subscription.activated",
        "subscription.charged",
        "subscription.completed",
        "subscription.updated",
        "subscription.pending",
        "subscription.halted",
        "subscription.cancelled",
        "subscription.paused",
        "subscription.resumed",
    }
)


async def store_event(
    db: AsyncSession,
    *,
    provider_event_id: str,
    event_type: str,
    payload_hash: str,
    payload: dict,
) -> bool:
    """Insert the event, or do nothing if the id was already recorded.

    Returns True iff this call inserted the row — the caller enqueues processing
    only for the first delivery.
    """
    inserted = (
        await db.execute(
            pg_insert(WebhookEvent)
            .values(
                provider_event_id=provider_event_id,
                event_type=event_type,
                payload_hash=payload_hash,
                payload=payload,
            )
            .on_conflict_do_nothing(index_elements=["provider_event_id"])
            .returning(WebhookEvent.id)
        )
    ).scalar_one_or_none()
    await db.commit()
    return inserted is not None


async def handle_event(db: AsyncSession, event: dict, *, provider_event_id: str) -> None:
    """Apply one verified event. Unknown and record-only types are a no-op."""
    if event.get("event") not in _SUBSCRIPTION_EVENTS:
        return
    entity = ((event.get("payload") or {}).get("subscription") or {}).get("entity") or {}
    subscription_id = entity.get("id")
    if not subscription_id:
        return
    await _sync_subscription(
        db,
        razorpay_client.retrieve_subscription(subscription_id),
        triggering_event_id=provider_event_id,
    )


async def _find_mirror(db: AsyncSession, subscription_id: str) -> Subscription | None:
    return (
        await db.execute(
            select(Subscription).where(
                Subscription.razorpay_subscription_id == subscription_id
            )
        )
    ).scalar_one_or_none()


def _unix(value: object) -> datetime.datetime | None:
    if value is None:
        return None
    return datetime.datetime.fromtimestamp(int(value), tz=datetime.UTC)


async def _sync_subscription(
    db: AsyncSession, sub: dict, *, triggering_event_id: str
) -> None:
    """Mirror one fetched Razorpay subscription and apply its plan transition."""
    subscription_id = sub.get("id")
    plan_id = sub.get("plan_id")
    status = sub.get("status")
    # Razorpay returns [] rather than {} for empty notes.
    notes = sub.get("notes") if isinstance(sub.get("notes"), dict) else {}

    row = await _find_mirror(db, subscription_id)
    if row is None:
        user_id = notes.get("user_id")
        if not user_id:
            raise ValueError("unmapped subscription")
        row = Subscription(
            user_id=uuid.UUID(str(user_id)), razorpay_subscription_id=subscription_id
        )
        db.add(row)

    row.razorpay_plan_id = plan_id
    row.status = status
    row.current_period_start = _unix(sub.get("current_start"))
    row.current_period_end = _unix(sub.get("current_end"))
    row.updated_at = datetime.datetime.now(datetime.UTC)
    row.billing_country = row.billing_country or notes.get("country")
    row.currency = row.currency or notes.get("currency")

    plan = plan_for_razorpay_plan(plan_id)
    if plan is not None and row.currency:
        row.tax_amount = tax_amount_minor(
            plan_price_minor(plan, row.currency), row.billing_country
        )
    await db.commit()

    if row.user_id is None:
        return
    user = await db.get(User, row.user_id)
    if user is None:
        return

    if status in _GRANTED_STATUSES:
        new_key = plan.key if plan is not None else "free"
    elif status in _REVOKED_STATUSES:
        new_key = "free"
    else:
        # created / authenticated / pending / paused: leave the plan as it was.
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
                "actor": "razorpay",
                "provider_event_id": triggering_event_id,
            },
        )
