"""Billing Checkout/cancel/webhook routes.

A minimal app mounts the auth and billing routers — the real api_server lifespan
probes Neo4j and a live LLM. Every Razorpay call is patched; webhook signatures
are generated locally with the HMAC-SHA256 scheme Razorpay uses.
"""

import asyncio
import hashlib
import hmac
import json
import os
import sys
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, event, select

from src.api.auth_api import router as auth_router
from src.api.billing_api import router as billing_router
from src.api.errors import install_error_handlers
from src.billing import razorpay_client
from src.billing.plans import clear_plan_cache
from src.config.settings import get_settings
from src.db.engine import get_engine
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
STARTER_INR_PLAN = "plan_starter_inr"

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


def _signed(event: dict, event_id: str | None) -> tuple[bytes, dict[str, str]]:
    raw = json.dumps(event).encode()
    signature = hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    headers = {"X-Razorpay-Signature": signature}
    if event_id is not None:
        headers["X-Razorpay-Event-Id"] = event_id
    return raw, headers


def _event() -> dict:
    return {
        "event": "subscription.activated",
        "payload": {"subscription": {"entity": {"id": "sub_hook"}}},
    }


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
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_test_secret")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("RAZORPAY_PLAN_STARTER_INR", STARTER_INR_PLAN)
    monkeypatch.setenv("RAZORPAY_PLAN_STARTER_USD", "plan_starter_usd")
    monkeypatch.setenv("RAZORPAY_PLAN_STUDIO_INR", "plan_studio_inr")
    monkeypatch.setenv("RAZORPAY_PLAN_STUDIO_USD", "plan_studio_usd")
    monkeypatch.setenv("QUEUE_MODE", "inline")
    get_settings.cache_clear()
    clear_plan_cache()


async def _delete_subscriptions(db, user_id) -> None:
    await db.execute(delete(Subscription).where(Subscription.user_id == user_id))
    await db.commit()


async def _add_subscription(db, user_id, *, status: str, subscription_id: str) -> None:
    db.add(
        Subscription(
            user_id=user_id,
            razorpay_subscription_id=subscription_id,
            razorpay_plan_id=STARTER_INR_PLAN,
            status=status,
            currency="INR",
            billing_country="IN",
        )
    )
    await db.commit()


async def _mirror(db, subscription_id: str) -> Subscription:
    return (
        await db.execute(
            select(Subscription)
            .where(Subscription.razorpay_subscription_id == subscription_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def _delete_webhook_event(db, event_id: str) -> None:
    await db.execute(
        delete(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
    )
    await db.commit()


@pytest.mark.asyncio
async def test_plans_are_public_and_come_from_the_server_table():
    settings = get_settings()
    async with _client() as client:
        response = await client.get("/api/v1/billing/plans")

    assert response.status_code == 200, response.text
    rows = response.json()
    assert [row["key"] for row in rows] == ["starter", "studio", "enterprise"]
    assert rows[0] == {
        "key": "starter",
        "prices": {
            "INR": settings.plan_starter_price_inr,
            "USD": settings.plan_starter_price_usd,
        },
        "price_label": None,
        "units": 8000,
        "max_agents": 12,
        "max_rounds": 4,
    }
    assert rows[2]["prices"] == {"INR": None, "USD": None}
    assert rows[2]["price_label"] == settings.plan_enterprise_price_label
    assert "free" not in [row["key"] for row in rows]


@requires_db
@pytest.mark.asyncio
async def test_checkout_and_cancel_are_503_when_billing_is_disabled(db):
    async with _client() as client:
        await _signup(client)
        checkout = await client.post(
            "/api/v1/billing/checkout",
            json={"plan": "starter", "currency": "INR", "country": "IN"},
            headers=_csrf(client),
        )
        cancel = await client.post(
            "/api/v1/billing/subscription/cancel", headers=_csrf(client)
        )

    assert checkout.status_code == 503
    assert cancel.status_code == 503
    assert checkout.json()["error"]["code"] == "service_unavailable"


@requires_db
@pytest.mark.asyncio
async def test_checkout_calls_razorpay_off_the_event_loop(db, billing_on, monkeypatch):
    import src.api.billing_api as billing_api

    threads: list[str] = []

    async def recording_to_thread(func, /, *args, **kwargs):
        threads.append(getattr(func, "__name__", str(func)))
        return func(*args, **kwargs)

    def create_subscription(**kwargs):
        return {"id": "sub_thread", "status": "created", "short_url": "https://rzp.test/t"}

    monkeypatch.setattr(billing_api.asyncio, "to_thread", recording_to_thread)
    monkeypatch.setattr(razorpay_client, "create_subscription", create_subscription)

    user_id = None
    try:
        async with _client() as client:
            user_id = await _signup(client)
            response = await client.post(
                "/api/v1/billing/checkout",
                json={"plan": "starter", "currency": "INR", "country": "IN"},
                headers=_csrf(client),
            )
        assert response.status_code == 200, response.text
        # Signup's argon2 hash also uses to_thread; the Razorpay call is the one under test.
        assert "create_subscription" in threads
    finally:
        if user_id is not None:
            await _delete_subscriptions(db, user_id)


@requires_db
@pytest.mark.asyncio
async def test_checkout_returns_the_short_url_and_writes_a_mirror_row(
    db, billing_on, monkeypatch
):
    captured: dict = {}

    def create_subscription(**kwargs):
        captured.update(kwargs)
        return {
            "id": "sub_new",
            "status": "created",
            "short_url": "https://rzp.test/checkout/sub_new",
        }

    monkeypatch.setattr(razorpay_client, "create_subscription", create_subscription)

    user_id = None
    try:
        async with _client() as client:
            user_id = await _signup(client)
            response = await client.post(
                "/api/v1/billing/checkout",
                json={"plan": "starter", "currency": "INR", "country": "IN"},
                headers=_csrf(client),
            )

        assert response.status_code == 200, response.text
        assert response.json() == {"url": "https://rzp.test/checkout/sub_new"}
        assert "rzp_test_secret" not in response.text

        assert captured["plan_id"] == STARTER_INR_PLAN
        assert captured["user_id"] == str(user_id)
        assert captured["plan_key"] == "starter"
        assert captured["currency"] == "INR"
        assert captured["country"] == "IN"
        assert captured["total_count"] == get_settings().razorpay_subscription_total_count

        mirror = await _mirror(db, "sub_new")
        assert mirror.user_id == user_id
        assert mirror.razorpay_plan_id == STARTER_INR_PLAN
        assert mirror.status == "created"
        assert mirror.currency == "INR"
        assert mirror.billing_country == "IN"
        assert mirror.tax_amount == 0
    finally:
        if user_id is not None:
            await _delete_subscriptions(db, user_id)


@requires_db
@pytest.mark.asyncio
async def test_checkout_is_409_while_a_plan_is_already_blocking(
    db, billing_on, monkeypatch
):
    calls: list[dict] = []
    monkeypatch.setattr(
        razorpay_client,
        "create_subscription",
        lambda **kwargs: calls.append(kwargs) or {},
    )

    user_id = None
    try:
        async with _client() as client:
            user_id = await _signup(client)
            await _add_subscription(
                db, user_id, status="active", subscription_id="sub_existing"
            )
            response = await client.post(
                "/api/v1/billing/checkout",
                json={"plan": "studio", "currency": "INR", "country": "IN"},
                headers=_csrf(client),
            )

        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "already_subscribed"
        assert calls == []
    finally:
        if user_id is not None:
            await _delete_subscriptions(db, user_id)


@requires_db
@pytest.mark.asyncio
async def test_checkout_locks_the_user_row_before_the_blocking_check(
    db, billing_on, monkeypatch
):
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    monkeypatch.setattr(
        razorpay_client,
        "create_subscription",
        lambda **kwargs: {
            "id": "sub_locked",
            "status": "created",
            "short_url": "https://rzp.test/checkout/sub_locked",
        },
    )

    user_id = None
    event.listen(get_engine().sync_engine, "before_cursor_execute", record)
    try:
        async with _client() as client:
            user_id = await _signup(client)
            statements.clear()
            response = await client.post(
                "/api/v1/billing/checkout",
                json={"plan": "starter", "currency": "INR", "country": "IN"},
                headers=_csrf(client),
            )

        assert response.status_code == 200, response.text
        lock = next(i for i, sql in enumerate(statements) if "FOR UPDATE" in sql)
        assert "FROM users" in statements[lock]
        check = next(i for i, sql in enumerate(statements) if "FROM subscriptions" in sql)
        assert lock < check
    finally:
        event.remove(get_engine().sync_engine, "before_cursor_execute", record)
        if user_id is not None:
            await _delete_subscriptions(db, user_id)


@requires_db
@pytest.mark.asyncio
async def test_checkout_is_422_for_an_unknown_currency(db, billing_on, monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(
        razorpay_client,
        "create_subscription",
        lambda **kwargs: calls.append(kwargs) or {},
    )

    user_id = None
    try:
        async with _client() as client:
            user_id = await _signup(client)
            response = await client.post(
                "/api/v1/billing/checkout",
                json={"plan": "starter", "currency": "EUR", "country": "IN"},
                headers=_csrf(client),
            )

        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "validation_error"
        assert calls == []
    finally:
        if user_id is not None:
            await _delete_subscriptions(db, user_id)


@requires_db
@pytest.mark.asyncio
async def test_cancel_sets_cancel_at_period_end_for_an_active_plan(
    db, billing_on, monkeypatch
):
    cancelled: list[tuple[str, bool]] = []

    def cancel_subscription(subscription_id, *, at_cycle_end):
        cancelled.append((subscription_id, at_cycle_end))
        return {"id": subscription_id, "status": "active"}

    monkeypatch.setattr(razorpay_client, "cancel_subscription", cancel_subscription)

    user_id = None
    try:
        async with _client() as client:
            user_id = await _signup(client)
            await _add_subscription(
                db, user_id, status="active", subscription_id="sub_active"
            )
            response = await client.post(
                "/api/v1/billing/subscription/cancel", headers=_csrf(client)
            )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "active"
        assert response.json()["plan"] == "starter"
        assert response.json()["cancel_at_period_end"] is True
        assert cancelled == [("sub_active", True)]

        mirror = await _mirror(db, "sub_active")
        assert mirror.status == "active"
        assert mirror.cancel_at_period_end is True
    finally:
        if user_id is not None:
            await _delete_subscriptions(db, user_id)


@requires_db
@pytest.mark.asyncio
async def test_cancel_is_immediate_for_a_plan_not_yet_active(
    db, billing_on, monkeypatch
):
    cancelled: list[tuple[str, bool]] = []

    def cancel_subscription(subscription_id, *, at_cycle_end):
        cancelled.append((subscription_id, at_cycle_end))
        return {"id": subscription_id, "status": "cancelled"}

    monkeypatch.setattr(razorpay_client, "cancel_subscription", cancel_subscription)

    user_id = None
    try:
        async with _client() as client:
            user_id = await _signup(client)
            await _add_subscription(
                db, user_id, status="authenticated", subscription_id="sub_pending"
            )
            response = await client.post(
                "/api/v1/billing/subscription/cancel", headers=_csrf(client)
            )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "cancelled"
        assert response.json()["cancel_at_period_end"] is False
        assert cancelled == [("sub_pending", False)]

        mirror = await _mirror(db, "sub_pending")
        assert mirror.status == "cancelled"
    finally:
        if user_id is not None:
            await _delete_subscriptions(db, user_id)


@requires_db
@pytest.mark.asyncio
async def test_webhook_records_once_per_event_id_and_rejects_a_bad_signature(
    db, billing_on, monkeypatch
):
    processed: list[str] = []

    async def fake_core(event_row_id: str) -> None:
        processed.append(event_row_id)

    monkeypatch.setattr(tasks, "process_razorpay_event_core", fake_core)
    event_id = f"evt_test_{uuid.uuid4().hex}"
    raw, headers = _signed(_event(), event_id)

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
                headers={
                    "X-Razorpay-Signature": "deadbeef",
                    "X-Razorpay-Event-Id": event_id,
                },
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
                        WebhookEvent.provider_event_id == event_id
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
        await _delete_webhook_event(db, event_id)


@requires_db
@pytest.mark.asyncio
async def test_webhook_is_400_without_an_event_id(billing_on, monkeypatch):
    async def fake_core(event_row_id: str) -> None:
        return None

    monkeypatch.setattr(tasks, "process_razorpay_event_core", fake_core)
    raw, headers = _signed(_event(), None)

    async with _client() as client:
        response = await client.post(
            "/api/v1/billing/webhook", content=raw, headers=headers
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "missing_event_id"


@requires_db
@pytest.mark.asyncio
async def test_webhook_succeeds_while_the_app_is_degraded(
    db, billing_on, monkeypatch
):
    async def fake_core(event_row_id: str) -> None:
        return None

    monkeypatch.setattr(tasks, "process_razorpay_event_core", fake_core)
    event_id = f"evt_test_{uuid.uuid4().hex}"
    raw, headers = _signed(_event(), event_id)

    _app.state.degraded = True
    try:
        async with _client() as client:
            response = await client.post(
                "/api/v1/billing/webhook", content=raw, headers=headers
            )
        assert response.status_code == 200
    finally:
        _app.state.degraded = False
        await _delete_webhook_event(db, event_id)


@requires_db
@pytest.mark.asyncio
async def test_webhook_needs_no_csrf_cookie_or_header(db, billing_on, monkeypatch):
    async def fake_core(event_row_id: str) -> None:
        return None

    monkeypatch.setattr(tasks, "process_razorpay_event_core", fake_core)
    event_id = f"evt_test_{uuid.uuid4().hex}"
    raw, headers = _signed(_event(), event_id)

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
        await _delete_webhook_event(db, event_id)


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
    event_id = f"evt_test_{uuid.uuid4().hex}"
    raw, headers = _signed(_event(), event_id)

    try:
        async with _client() as client:
            response = await client.post(
                "/api/v1/billing/webhook", content=raw, headers=headers
            )

        assert response.status_code == 200
        assert captured["func"] is tasks.process_razorpay_event
        assert captured["retry"] is not None
        assert captured["retry"].max == get_settings().job_retry_max
    finally:
        await _delete_webhook_event(db, event_id)


@requires_db
@pytest.mark.asyncio
async def test_webhook_fails_closed_without_a_secret(db, monkeypatch):
    """No secret means no verifiable signature — refuse instead of using ""."""
    # Billing off is the only reachable state here: the validator forbids
    # billing_enabled=True without a secret.
    monkeypatch.delenv("BILLING_ENABLED", raising=False)
    monkeypatch.delenv("RAZORPAY_WEBHOOK_SECRET", raising=False)
    get_settings.cache_clear()

    event_id = f"evt_test_{uuid.uuid4().hex}"
    raw, headers = _signed(_event(), event_id)

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
                        WebhookEvent.provider_event_id == event_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert rows == []
    finally:
        await _delete_webhook_event(db, event_id)
