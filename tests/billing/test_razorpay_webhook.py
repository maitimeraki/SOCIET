"""Razorpay webhook and client: signature, idempotency, plan state machine.

Network-free: the subscription fetch is patched with a plain dict, and the SDK
client is driven through a fake HTTP session. DB-backed tests need DATABASE_URL.
"""

import hashlib
import hmac
import json
import os
import time
import uuid

import pytest
import razorpay
from razorpay.errors import SignatureVerificationError
from sqlalchemy import delete, select

from src.billing import razorpay_client, webhook
from src.billing.plans import clear_plan_cache
from src.config.settings import get_settings
from src.db.models import AuditLog, Subscription, User, WebhookEvent

SECRET = "whsec_test"

needs_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)


@pytest.fixture(autouse=True)
def _razorpay_plans(monkeypatch):
    """Configured plan ids must be visible to the cached plan registry."""
    monkeypatch.setenv("RAZORPAY_PLAN_STARTER_INR", "plan_starter_inr")
    monkeypatch.setenv("RAZORPAY_PLAN_STARTER_USD", "plan_starter_usd")
    monkeypatch.setenv("RAZORPAY_PLAN_STUDIO_INR", "plan_studio_inr")
    monkeypatch.setenv("RAZORPAY_PLAN_STUDIO_USD", "plan_studio_usd")
    get_settings.cache_clear()
    clear_plan_cache()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()
    clear_plan_cache()


def _entity(
    *,
    status: str = "active",
    plan_id: str = "plan_starter_inr",
    subscription_id: str = "sub_1",
    notes: dict | list = [],  # Razorpay returns [] for empty notes
) -> dict:
    now = 1_700_000_000
    return {
        "id": subscription_id,
        "plan_id": plan_id,
        "status": status,
        "current_start": now,
        "current_end": now + 30 * 86_400,
        "notes": notes,
        "total_count": 120,
        "paid_count": 0,
    }


def _event(event_type: str, subscription_id: str = "sub_1") -> dict:
    return {
        "entity": "event",
        "event": event_type,
        "contains": ["subscription"],
        "payload": {"subscription": {"entity": {"id": subscription_id}}},
    }


async def _make_user(factory, plan: str = "free") -> uuid.UUID:
    async with factory() as db:
        user = User(
            email=f"razorpay-{uuid.uuid4().hex}@example.com",
            password_hash="not-a-real-hash",
            plan_key=plan,
        )
        db.add(user)
        await db.flush()
        user_id = user.id
        await db.commit()
    return user_id


async def _make_mirror(factory, user_id: uuid.UUID, subscription_id: str = "sub_1") -> None:
    async with factory() as db:
        db.add(
            Subscription(
                user_id=user_id,
                razorpay_subscription_id=subscription_id,
                status="created",
                currency="INR",
                billing_country="IN",
            )
        )
        await db.commit()


async def _cleanup(factory, *, user_ids=(), event_ids=()) -> None:
    async with factory() as db:
        for user_id in user_ids:
            await db.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
            await db.execute(delete(Subscription).where(Subscription.user_id == user_id))
            await db.execute(delete(User).where(User.id == user_id))
        if event_ids:
            await db.execute(
                delete(WebhookEvent).where(WebhookEvent.provider_event_id.in_(event_ids))
            )
        await db.commit()


def test_signature_accepts_a_valid_hmac_and_rejects_tampering():
    raw = b'{"event": "subscription.activated"}'
    signature = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()

    razorpay_client.verify_webhook_signature(raw, signature, secret=SECRET)

    with pytest.raises(SignatureVerificationError):
        razorpay_client.verify_webhook_signature(raw + b" ", signature, secret=SECRET)
    with pytest.raises(SignatureVerificationError):
        razorpay_client.verify_webhook_signature(raw, signature, secret="whsec_other")


def test_missing_signature_is_rejected():
    with pytest.raises(ValueError):
        razorpay_client.verify_webhook_signature(b"{}", None, secret=SECRET)


class _FakeResponse:
    status_code = 200

    def json(self):
        return {"id": "sub_1", "status": "created"}


class _FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _FakeResponse()


def test_create_subscription_forwards_timeout_and_notes(monkeypatch):
    session = _FakeSession()
    client = razorpay.Client(session=session, auth=("rzp_test_key", "secret"))
    monkeypatch.setattr(razorpay_client, "get_client", lambda: client)

    before = int(time.time())
    result = razorpay_client.create_subscription(
        plan_id="plan_starter_inr",
        user_id="user-1",
        plan_key="starter",
        currency="INR",
        country="IN",
        total_count=120,
    )
    after = int(time.time())

    _, kwargs = session.calls[0]
    payload = json.loads(kwargs["data"])
    expire_by = payload.pop("expire_by")
    assert result == {"id": "sub_1", "status": "created"}
    assert kwargs["timeout"] == razorpay_client.TIMEOUT_SECONDS
    assert before + razorpay_client.AUTHORISATION_WINDOW_SECONDS <= expire_by
    assert expire_by <= after + razorpay_client.AUTHORISATION_WINDOW_SECONDS
    assert payload == {
        "plan_id": "plan_starter_inr",
        "total_count": 120,
        "customer_notify": 1,
        "notes": {"user_id": "user-1", "plan": "starter", "currency": "INR", "country": "IN"},
    }


@needs_db
@pytest.mark.asyncio
async def test_store_event_dedupes_on_provider_event_id(session_factory):
    factory = session_factory
    event_id = f"evt_{uuid.uuid4().hex}"
    try:
        async with factory() as db:
            first = await webhook.store_event(
                db,
                provider_event_id=event_id,
                event_type="subscription.activated",
                payload_hash="a" * 64,
                payload={},
            )
        async with factory() as db:
            second = await webhook.store_event(
                db,
                provider_event_id=event_id,
                event_type="subscription.activated",
                payload_hash="b" * 64,
                payload={},
            )
        async with factory() as db:
            rows = (
                (
                    await db.execute(
                        select(WebhookEvent).where(
                            WebhookEvent.provider_event_id == event_id
                        )
                    )
                )
                .scalars()
                .all()
            )

        assert first is True
        assert second is False
        assert len(rows) == 1
        assert rows[0].payload_hash == "a" * 64
    finally:
        await _cleanup(factory, event_ids=[event_id])


@needs_db
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "start_plan", "expected_plan"),
    [
        ("active", "free", "starter"),
        ("halted", "starter", "free"),
        ("cancelled", "starter", "free"),
        ("completed", "starter", "free"),
        ("pending", "starter", "starter"),
        ("authenticated", "free", "free"),
    ],
)
async def test_subscription_status_drives_the_plan(
    session_factory, monkeypatch, status, start_plan, expected_plan
):
    factory = session_factory
    user_id = await _make_user(factory, plan=start_plan)
    await _make_mirror(factory, user_id)
    monkeypatch.setattr(
        razorpay_client, "retrieve_subscription", lambda _id: _entity(status=status)
    )

    try:
        async with factory() as db:
            await webhook.handle_event(
                db, _event("subscription.updated"), provider_event_id="evt_status"
            )
        async with factory() as db:
            user = await db.get(User, user_id)

        assert user.plan_key == expected_plan
    finally:
        await _cleanup(factory, user_ids=[user_id])


@needs_db
@pytest.mark.asyncio
async def test_missing_mirror_is_created_from_notes(session_factory, monkeypatch):
    factory = session_factory
    user_id = await _make_user(factory)
    notes = {"user_id": str(user_id), "currency": "USD", "country": "US"}
    monkeypatch.setattr(
        razorpay_client,
        "retrieve_subscription",
        lambda _id: _entity(
            subscription_id="sub_new", plan_id="plan_starter_usd", notes=notes
        ),
    )

    try:
        async with factory() as db:
            await webhook.handle_event(
                db, _event("subscription.activated", "sub_new"), provider_event_id="evt_new"
            )
        async with factory() as db:
            row = (
                await db.execute(
                    select(Subscription).where(
                        Subscription.razorpay_subscription_id == "sub_new"
                    )
                )
            ).scalar_one()
            user = await db.get(User, user_id)

        assert row.user_id == user_id
        assert (row.currency, row.billing_country) == ("USD", "US")
        assert user.plan_key == "starter"
    finally:
        await _cleanup(factory, user_ids=[user_id])


@needs_db
@pytest.mark.asyncio
async def test_unmapped_subscription_without_notes_is_rejected(
    session_factory, monkeypatch
):
    factory = session_factory
    monkeypatch.setattr(
        razorpay_client,
        "retrieve_subscription",
        lambda _id: _entity(subscription_id="sub_orphan", notes={}),
    )

    async with factory() as db:
        with pytest.raises(ValueError, match="unmapped subscription"):
            await webhook.handle_event(
                db, _event("subscription.activated", "sub_orphan"), provider_event_id="evt_x"
            )
