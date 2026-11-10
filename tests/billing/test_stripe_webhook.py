"""Stripe webhook: signature verification, idempotency, plan state machine.

DB-backed and network-free — every Stripe retrieve is patched with a plain
dict, and signatures are generated locally with Stripe's own helper.
"""

import asyncio
import datetime
import os
import sys
import uuid

import pytest
import stripe
from sqlalchemy import delete, select

from src.billing import stripe_client, webhook
from src.billing.plans import clear_plan_cache
from src.config.settings import get_settings
from src.db.models import AuditLog, Subscription, User, WebhookEvent
from src.jobs import tasks

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)

SECRET = "whsec_test"


@pytest.fixture(autouse=True)
def _stripe_prices(monkeypatch):
    """Configured prices must be visible to the cached plan registry."""
    monkeypatch.setenv("STRIPE_PRICE_STARTER", "price_starter")
    monkeypatch.setenv("STRIPE_PRICE_STUDIO", "price_studio")
    get_settings.cache_clear()
    clear_plan_cache()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()
    clear_plan_cache()


def _now() -> int:
    return int(datetime.datetime.now(datetime.UTC).timestamp())


def _subscription(
    *,
    status: str = "active",
    price_id: str = "price_starter",
    cancel_at_period_end: bool = False,
    subscription_id: str = "sub_1",
    customer_id: str = "cus_1",
) -> dict:
    return {
        "id": subscription_id,
        "customer": customer_id,
        "status": status,
        "current_period_start": _now(),
        "current_period_end": _now() + 30 * 86_400,
        "cancel_at_period_end": cancel_at_period_end,
        "items": {"data": [{"price": {"id": price_id}}]},
    }


def _event(event_type: str, obj: dict) -> dict:
    return {
        "id": f"evt_{uuid.uuid4().hex}",
        "type": event_type,
        "data": {"object": obj},
    }


async def _make_user(factory, plan: str = "free") -> uuid.UUID:
    async with factory() as db:
        user = User(
            email=f"stripe-{uuid.uuid4().hex}@example.com",
            password_hash="not-a-real-hash",
            plan_key=plan,
        )
        db.add(user)
        await db.flush()
        user_id = user.id
        await db.commit()
    return user_id


async def _make_mirror(
    factory, user_id: uuid.UUID, *, customer_id: str = "cus_1", status: str = "incomplete"
) -> None:
    async with factory() as db:
        db.add(
            Subscription(
                user_id=user_id, stripe_customer_id=customer_id, status=status
            )
        )
        await db.commit()


async def _record_event(
    factory, event: dict, *, received_at: datetime.datetime | None = None
) -> uuid.UUID:
    async with factory() as db:
        row = WebhookEvent(
            provider_event_id=event["id"],
            event_type=event["type"],
            payload_hash="0" * 64,
            payload=event,
        )
        if received_at is not None:
            row.received_at = received_at
        db.add(row)
        await db.flush()
        row_id = row.id
        await db.commit()
    return row_id


async def _cleanup(
    factory, *, user_id: uuid.UUID | None = None, event_ids: list[str] | None = None
) -> None:
    async with factory() as db:
        if user_id is not None:
            await db.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
            await db.execute(
                delete(Subscription).where(Subscription.user_id == user_id)
            )
            await db.execute(delete(User).where(User.id == user_id))
        if event_ids:
            await db.execute(
                delete(WebhookEvent).where(
                    WebhookEvent.provider_event_id.in_(event_ids)
                )
            )
        await db.commit()


def test_signature_accepts_a_valid_header_and_rejects_tampering():
    raw = b'{"id": "evt_1", "type": "customer.updated"}'
    header = stripe.WebhookSignature.generate_signature_header(
        raw.decode(), SECRET
    )

    webhook.verify_signature(raw, header, secret=SECRET, tolerance=300)

    with pytest.raises(Exception):
        webhook.verify_signature(raw + b"tampered", header, secret=SECRET, tolerance=300)
    with pytest.raises(Exception):
        webhook.verify_signature(raw, header, secret="whsec_other", tolerance=300)


@pytest.mark.asyncio
async def test_store_event_is_idempotent(session_factory):
    factory = session_factory
    event = _event("customer.updated", {})
    try:
        async with factory() as db:
            assert await webhook.store_event(db, event, "a" * 64) is True
        async with factory() as db:
            assert await webhook.store_event(db, event, "b" * 64) is False

        async with factory() as db:
            rows = (
                (
                    await db.execute(
                        select(WebhookEvent).where(
                            WebhookEvent.provider_event_id == event["id"]
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert len(rows) == 1
        assert rows[0].payload_hash == "a" * 64
    finally:
        await _cleanup(factory, event_ids=[event["id"]])


@pytest.mark.asyncio
async def test_active_subscription_grants_the_plan_and_audits(
    session_factory, monkeypatch
):
    factory = session_factory
    user_id = await _make_user(factory)
    await _make_mirror(factory, user_id)
    event = _event("customer.subscription.updated", {"id": "sub_1"})
    row_id = await _record_event(factory, event)
    monkeypatch.setattr(
        stripe_client, "retrieve_subscription", lambda _id: _subscription()
    )

    try:
        await tasks.process_stripe_event_core(str(row_id))

        async with factory() as db:
            user = await db.get(User, user_id)
            mirror = (
                await db.execute(
                    select(Subscription).where(Subscription.user_id == user_id)
                )
            ).scalar_one()
            audits = (
                (
                    await db.execute(
                        select(AuditLog).where(
                            AuditLog.user_id == user_id,
                            AuditLog.action == "plan_change",
                        )
                    )
                )
                .scalars()
                .all()
            )
            row = await db.get(WebhookEvent, row_id)

        assert user.plan_key == "starter"
        assert mirror.status == "active"
        assert mirror.stripe_subscription_id == "sub_1"
        assert mirror.price_id == "price_starter"
        assert len(audits) == 1
        assert audits[0].meta["actor"] == "stripe"
        assert audits[0].meta["from"] == "free"
        assert audits[0].meta["to"] == "starter"
        assert audits[0].meta["stripe_event_id"] == event["id"]
        assert row.status == "processed"
        assert row.processed_at is not None
    finally:
        await _cleanup(factory, user_id=user_id, event_ids=[event["id"]])


@pytest.mark.asyncio
async def test_cancel_at_period_end_keeps_access_while_active(
    session_factory, monkeypatch
):
    factory = session_factory
    user_id = await _make_user(factory)
    await _make_mirror(factory, user_id)
    event = _event("customer.subscription.updated", {"id": "sub_1"})
    row_id = await _record_event(factory, event)
    monkeypatch.setattr(
        stripe_client,
        "retrieve_subscription",
        lambda _id: _subscription(cancel_at_period_end=True),
    )

    try:
        await tasks.process_stripe_event_core(str(row_id))

        async with factory() as db:
            user = await db.get(User, user_id)
            mirror = (
                await db.execute(
                    select(Subscription).where(Subscription.user_id == user_id)
                )
            ).scalar_one()

        assert user.plan_key == "starter"
        assert mirror.cancel_at_period_end is True
    finally:
        await _cleanup(factory, user_id=user_id, event_ids=[event["id"]])


@pytest.mark.asyncio
async def test_deleted_subscription_revokes_to_free(session_factory, monkeypatch):
    factory = session_factory
    user_id = await _make_user(factory, plan="starter")
    await _make_mirror(factory, user_id, status="active")
    event = _event("customer.subscription.deleted", {"id": "sub_1"})
    row_id = await _record_event(factory, event)
    monkeypatch.setattr(
        stripe_client,
        "retrieve_subscription",
        lambda _id: _subscription(status="canceled"),
    )

    try:
        await tasks.process_stripe_event_core(str(row_id))

        async with factory() as db:
            user = await db.get(User, user_id)

        assert user.plan_key == "free"
    finally:
        await _cleanup(factory, user_id=user_id, event_ids=[event["id"]])


@pytest.mark.asyncio
async def test_unknown_price_resolves_to_free(session_factory, monkeypatch):
    factory = session_factory
    user_id = await _make_user(factory, plan="starter")
    await _make_mirror(factory, user_id, status="active")
    event = _event("customer.subscription.updated", {"id": "sub_1"})
    row_id = await _record_event(factory, event)
    monkeypatch.setattr(
        stripe_client,
        "retrieve_subscription",
        lambda _id: _subscription(price_id="price_not_in_any_plan"),
    )

    try:
        await tasks.process_stripe_event_core(str(row_id))

        async with factory() as db:
            user = await db.get(User, user_id)

        assert user.plan_key == "free"
    finally:
        await _cleanup(factory, user_id=user_id, event_ids=[event["id"]])


@pytest.mark.asyncio
async def test_past_due_leaves_the_plan_unchanged(session_factory, monkeypatch):
    factory = session_factory
    user_id = await _make_user(factory, plan="starter")
    await _make_mirror(factory, user_id, status="active")
    event = _event("customer.subscription.updated", {"id": "sub_1"})
    row_id = await _record_event(factory, event)
    monkeypatch.setattr(
        stripe_client,
        "retrieve_subscription",
        lambda _id: _subscription(status="past_due"),
    )

    try:
        await tasks.process_stripe_event_core(str(row_id))

        async with factory() as db:
            user = await db.get(User, user_id)
            mirror = (
                await db.execute(
                    select(Subscription).where(Subscription.user_id == user_id)
                )
            ).scalar_one()

        assert user.plan_key == "starter"
        assert mirror.status == "past_due"
    finally:
        await _cleanup(factory, user_id=user_id, event_ids=[event["id"]])


def _modern_subscription(
    *,
    status: str = "active",
    price_id: str = "price_starter",
    subscription_id: str = "sub_1",
    customer_id: str = "cus_1",
) -> dict:
    """API 2025-03-31 (Basil) shape: the period lives on the item."""
    now = _now()
    return {
        "id": subscription_id,
        "customer": customer_id,
        "status": status,
        "cancel_at_period_end": False,
        "items": {
            "data": [
                {
                    "price": {"id": price_id},
                    "current_period_start": now,
                    "current_period_end": now + 30 * 86_400,
                }
            ]
        },
    }


@pytest.mark.asyncio
async def test_modern_subscription_shape_reads_the_item_period(
    session_factory, monkeypatch
):
    factory = session_factory
    user_id = await _make_user(factory)
    await _make_mirror(factory, user_id)
    event = _event("customer.subscription.updated", {"id": "sub_1"})
    row_id = await _record_event(factory, event)
    modern = _modern_subscription()
    monkeypatch.setattr(
        stripe_client, "retrieve_subscription", lambda _id: modern
    )

    try:
        await tasks.process_stripe_event_core(str(row_id))

        async with factory() as db:
            user = await db.get(User, user_id)
            mirror = (
                await db.execute(
                    select(Subscription).where(Subscription.user_id == user_id)
                )
            ).scalar_one()

        assert user.plan_key == "starter"
        assert mirror.current_period_start is not None
        assert mirror.current_period_end is not None
        assert (
            mirror.current_period_end - mirror.current_period_start
        ) == datetime.timedelta(days=30)
    finally:
        await _cleanup(factory, user_id=user_id, event_ids=[event["id"]])


@pytest.mark.asyncio
async def test_modern_invoice_shape_finds_the_subscription(
    session_factory, monkeypatch
):
    factory = session_factory
    user_id = await _make_user(factory)
    await _make_mirror(factory, user_id)
    # API 2025-03-31 (Basil): the invoice references the subscription under
    # parent.subscription_details, not at the root.
    event = _event(
        "invoice.paid",
        {"parent": {"subscription_details": {"subscription": "sub_1"}}},
    )
    row_id = await _record_event(factory, event)
    monkeypatch.setattr(
        stripe_client, "retrieve_subscription", lambda _id: _subscription()
    )

    try:
        await tasks.process_stripe_event_core(str(row_id))

        async with factory() as db:
            user = await db.get(User, user_id)

        assert user.plan_key == "starter"
    finally:
        await _cleanup(factory, user_id=user_id, event_ids=[event["id"]])


@pytest.mark.asyncio
async def test_reconcile_replays_a_stranded_pending_event(
    session_factory, monkeypatch
):
    factory = session_factory
    event = _event("customer.updated", {"id": "cus_1"})
    stale = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=5)
    row_id = await _record_event(factory, event, received_at=stale)
    # Any leftover mirror row from another test must not hit the network.
    monkeypatch.setattr(
        stripe_client, "retrieve_subscription", lambda _id: _subscription()
    )

    try:
        counts = await tasks.reconcile_subscriptions_core()

        async with factory() as db:
            row = await db.get(WebhookEvent, row_id)

        assert counts["webhook_retried"] >= 1
        assert row.status == "processed"
        assert row.processed_at is not None
    finally:
        await _cleanup(factory, event_ids=[event["id"]])


@pytest.mark.asyncio
async def test_unmapped_subscription_marks_the_event_failed(
    session_factory, monkeypatch
):
    factory = session_factory
    event = _event(
        "customer.subscription.updated",
        {"id": "sub_unknown", "customer": "cus_unknown"},
    )
    row_id = await _record_event(factory, event)
    monkeypatch.setattr(
        stripe_client,
        "retrieve_subscription",
        lambda _id: _subscription(
            subscription_id="sub_unknown", customer_id="cus_unknown"
        ),
    )

    try:
        with pytest.raises(ValueError, match="unmapped subscription"):
            await tasks.process_stripe_event_core(str(row_id))

        async with factory() as db:
            row = await db.get(WebhookEvent, row_id)

        assert row.status == "failed"
        assert "unmapped subscription" in row.error
    finally:
        await _cleanup(factory, event_ids=[event["id"]])
