"""Billing Checkout/Portal/webhook routes (task 8).

A minimal app mounts the auth and billing routers — the real api_server lifespan
probes Neo4j and a live LLM. Every Stripe call is patched; signatures are
generated locally.
"""

import asyncio
import json
import os
import sys
import uuid

import pytest
import stripe
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from src.api.auth_api import router as auth_router
from src.api.billing_api import router as billing_router
from src.api.errors import install_error_handlers
from src.billing.plans import clear_plan_cache
from src.config.settings import get_settings
from src.db.models import Subscription, WebhookEvent
from src.jobs import queue as jobs_queue
from src.jobs import tasks

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)

PASSWORD = "hunter2hunter2"
WEBHOOK_SECRET = "whsec_test"

_app = FastAPI()
install_error_handlers(_app)
_app.include_router(auth_router)
_app.include_router(billing_router)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=_app), base_url="http://testserver")


def _email() -> str:
    return f"auth-test-billing-{uuid.uuid4().hex[:10]}@example.com"


def _csrf(client: AsyncClient) -> dict[str, str]:
    """The double-submit header matching the cookie signup just set."""
    return {"X-CSRF-Token": client.cookies.get("csrf")}


async def _signup(client: AsyncClient) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": _email(),
            "password": PASSWORD,
            "accept_terms": True,
            "age_confirmed": True,
        },
    )
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


def _signed(event: dict) -> tuple[bytes, dict[str, str]]:
    raw = json.dumps(event).encode()
    header = stripe.WebhookSignature.generate_signature_header(
        raw.decode(), WEBHOOK_SECRET
    )
    return raw, {"Stripe-Signature": header}


@pytest.fixture(autouse=True)
def _fresh_settings(monkeypatch):
    """Every test starts from the environment as restored by pytest."""
    get_settings.cache_clear()
    clear_plan_cache()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()
    clear_plan_cache()


@pytest.fixture
def billing_on(monkeypatch):
    monkeypatch.setenv("BILLING_ENABLED", "true")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("STRIPE_PRICE_STARTER", "price_starter")
    monkeypatch.setenv("STRIPE_PRICE_STUDIO", "price_studio")
    monkeypatch.setenv("QUEUE_MODE", "inline")
    get_settings.cache_clear()
    clear_plan_cache()


async def _delete_subscriptions(db, user_id) -> None:
    await db.execute(delete(Subscription).where(Subscription.user_id == user_id))
    await db.commit()


@requires_db
@pytest.mark.asyncio
async def test_checkout_and_portal_are_503_when_billing_is_disabled(db):
    async with _client() as client:
        await _signup(client)
        checkout = await client.post(
            "/api/v1/billing/checkout",
            json={"plan": "starter"},
            headers=_csrf(client),
        )
        portal = await client.post("/api/v1/billing/portal", headers=_csrf(client))

    assert checkout.status_code == 503
    assert portal.status_code == 503
    assert checkout.json()["error"]["code"] == "service_unavailable"


@requires_db
@pytest.mark.asyncio
async def test_checkout_creates_a_subscription_session(db, billing_on, monkeypatch):
    captured: dict[str, dict] = {}

    def fake_customer_create(**kwargs):
        captured["customer"] = kwargs
        return {"id": "cus_test"}

    def fake_session_create(**kwargs):
        captured["session"] = kwargs
        return {"id": "cs_test", "url": "https://checkout.stripe.test/session"}

    monkeypatch.setattr(stripe.Customer, "create", fake_customer_create)
    monkeypatch.setattr(stripe.checkout.Session, "create", fake_session_create)

    user_id = None
    try:
        async with _client() as client:
            user_id = await _signup(client)
            response = await client.post(
                "/api/v1/billing/checkout",
                json={"plan": "starter"},
                headers=_csrf(client),
            )

        assert response.status_code == 200, response.text
        assert response.json() == {"url": "https://checkout.stripe.test/session"}
        assert "pk_" not in response.text
        assert "sk_" not in response.text

        session = captured["session"]
        assert session["mode"] == "subscription"
        assert session["line_items"] == [{"price": "price_starter", "quantity": 1}]
        assert session["client_reference_id"] == str(user_id)
        assert session["customer"] == "cus_test"
        assert session["automatic_tax"] == {"enabled": True}
        assert session["subscription_data"]["metadata"]["user_id"] == str(user_id)
        assert session["success_url"].endswith("/pricing?checkout=success")
        assert session["cancel_url"].endswith("/pricing?checkout=cancel")

        mirror = (
            await db.execute(
                select(Subscription).where(Subscription.user_id == user_id)
            )
        ).scalar_one()
        assert mirror.stripe_customer_id == "cus_test"
        assert mirror.status == "incomplete"
    finally:
        if user_id is not None:
            await _delete_subscriptions(db, user_id)


@requires_db
@pytest.mark.asyncio
async def test_portal_is_404_without_a_customer_and_200_with_one(
    db, billing_on, monkeypatch
):
    captured: dict[str, str] = {}

    def fake_portal_create(**kwargs):
        captured.update(kwargs)
        return {"url": "https://billing.stripe.test/portal"}

    monkeypatch.setattr(stripe.billing_portal.Session, "create", fake_portal_create)

    user_id = None
    try:
        async with _client() as client:
            user_id = await _signup(client)
            missing = await client.post(
                "/api/v1/billing/portal", headers=_csrf(client)
            )
            assert missing.status_code == 404

            db.add(
                Subscription(
                    user_id=user_id,
                    stripe_customer_id="cus_portal",
                    status="active",
                )
            )
            await db.commit()

            response = await client.post(
                "/api/v1/billing/portal", headers=_csrf(client)
            )

        assert response.status_code == 200, response.text
        assert response.json() == {"url": "https://billing.stripe.test/portal"}
        assert captured["customer"] == "cus_portal"
        assert captured["return_url"].endswith("/account")
    finally:
        if user_id is not None:
            await _delete_subscriptions(db, user_id)


@requires_db
@pytest.mark.asyncio
async def test_webhook_records_once_and_rejects_a_bad_signature(
    db, billing_on, monkeypatch
):
    processed: list[str] = []

    async def fake_core(event_row_id: str) -> None:
        processed.append(event_row_id)

    monkeypatch.setattr(tasks, "process_stripe_event_core", fake_core)
    event = {
        "id": f"evt_test_{uuid.uuid4().hex}",
        "type": "customer.updated",
        "data": {"object": {"id": "cus_1"}},
    }
    raw, headers = _signed(event)

    try:
        async with _client() as client:
            first = await client.post(
                "/api/v1/billing/webhook", content=raw, headers=headers
            )
            second = await client.post(
                "/api/v1/billing/webhook", content=raw, headers=headers
            )
            bad = await client.post(
                "/api/v1/billing/webhook",
                content=raw,
                headers={"Stripe-Signature": "t=1,v1=deadbeef"},
            )

        assert first.status_code == 200
        assert first.json() == {"received": True}
        assert second.status_code == 200
        assert bad.status_code == 400
        assert bad.json()["error"]["code"] == "invalid_signature"

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
        assert rows[0].status == "pending"
        assert len(processed) == 1
    finally:
        await db.execute(
            delete(WebhookEvent).where(WebhookEvent.provider_event_id == event["id"])
        )
        await db.commit()


@requires_db
@pytest.mark.asyncio
async def test_webhook_succeeds_while_the_app_is_degraded(
    db, billing_on, monkeypatch
):
    async def fake_core(event_row_id: str) -> None:
        return None

    monkeypatch.setattr(tasks, "process_stripe_event_core", fake_core)
    event = {
        "id": f"evt_test_{uuid.uuid4().hex}",
        "type": "customer.updated",
        "data": {"object": {"id": "cus_1"}},
    }
    raw, headers = _signed(event)

    _app.state.degraded = True
    try:
        async with _client() as client:
            response = await client.post(
                "/api/v1/billing/webhook", content=raw, headers=headers
            )
        assert response.status_code == 200
    finally:
        _app.state.degraded = False
        await db.execute(
            delete(WebhookEvent).where(WebhookEvent.provider_event_id == event["id"])
        )
        await db.commit()


@requires_db
@pytest.mark.asyncio
async def test_webhook_needs_no_csrf_cookie_or_header(db, billing_on, monkeypatch):
    async def fake_core(event_row_id: str) -> None:
        return None

    monkeypatch.setattr(tasks, "process_stripe_event_core", fake_core)
    event = {
        "id": f"evt_test_{uuid.uuid4().hex}",
        "type": "customer.updated",
        "data": {"object": {"id": "cus_1"}},
    }
    raw, headers = _signed(event)

    try:
        async with _client() as client:
            # Signup sets both the sid and csrf cookies; the webhook is posted
            # without the X-CSRF-Token header — a router-level CSRF guard would
            # 403 it.
            await _signup(client)
            assert client.cookies.get("sid")
            assert client.cookies.get("csrf")

            response = await client.post(
                "/api/v1/billing/webhook", content=raw, headers=headers
            )
        assert response.status_code == 200
    finally:
        await db.execute(
            delete(WebhookEvent).where(WebhookEvent.provider_event_id == event["id"])
        )
        await db.commit()


@requires_db
@pytest.mark.asyncio
async def test_webhook_enqueues_with_the_retry_policy(db, billing_on, monkeypatch):
    monkeypatch.setenv("QUEUE_MODE", "rq")
    get_settings.cache_clear()
    captured: dict = {}

    class _Queue:
        def enqueue(self, func, *args, **kwargs):
            captured["func"] = func
            captured["args"] = args
            captured["retry"] = kwargs.get("retry")

    monkeypatch.setattr(jobs_queue, "get_queue", lambda: _Queue())
    event = {
        "id": f"evt_test_{uuid.uuid4().hex}",
        "type": "customer.updated",
        "data": {"object": {"id": "cus_1"}},
    }
    raw, headers = _signed(event)

    try:
        async with _client() as client:
            response = await client.post(
                "/api/v1/billing/webhook", content=raw, headers=headers
            )

        assert response.status_code == 200
        assert captured["func"] is tasks.process_stripe_event
        assert captured["retry"] is not None
        assert captured["retry"].max == get_settings().job_retry_max
    finally:
        await db.execute(
            delete(WebhookEvent).where(WebhookEvent.provider_event_id == event["id"])
        )
        await db.commit()


@requires_db
@pytest.mark.asyncio
async def test_webhook_fails_closed_without_a_secret(db, monkeypatch):
    """No secret means no verifiable signature — refuse instead of using ""."""
    # Billing off is the only reachable state here: the validator forbids
    # billing_enabled=True without a secret.
    monkeypatch.delenv("BILLING_ENABLED", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    get_settings.cache_clear()

    event = {
        "id": f"evt_test_{uuid.uuid4().hex}",
        "type": "customer.updated",
        "data": {"object": {"id": "cus_1"}},
    }
    raw, headers = _signed(event)

    try:
        async with _client() as client:
            response = await client.post(
                "/api/v1/billing/webhook", content=raw, headers=headers
            )

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "service_unavailable"

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
        assert rows == []
    finally:
        await db.execute(
            delete(WebhookEvent).where(WebhookEvent.provider_event_id == event["id"])
        )
        await db.commit()
