"""Billing HTTP surface: plan card, usage, Razorpay Checkout, cancel, webhook.

The webhook sits under ``/api/`` with no CSRF dependency and no
``service_available`` gate — payment must keep working while the LLM is down.
Checkout and cancel are state-changing user actions and do carry CSRF.
"""

import asyncio
import datetime
import hashlib
import json
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.cookies import verify_csrf
from src.auth.deps import current_user
from src.billing import razorpay_client
from src.billing import webhook as webhook_events
from src.billing.entitlements import resolve_entitlements
from src.billing.plans import (
    SUPPORTED_CURRENCIES,
    get_plan,
    plan_for_razorpay_plan,
    plan_price_minor,
)
from src.billing.tax import tax_amount_minor
from src.config.settings import get_settings
from src.db.engine import get_db
from src.db.models import Subscription, User, WebhookEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])

PAID_PLANS = ("starter", "studio")
_COUNTRY_CODE = re.compile(r"^[A-Z]{2}$")


def _service_unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "service_unavailable",
            "message": "Billing is not available.",
        },
    )


def _upstream_error() -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={
            "code": "upstream_error",
            "message": "The payment provider could not complete the request.",
        },
    )


def _validation_error(message: str) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"code": "validation_error", "message": message},
    )


class UsageOut(BaseModel):
    plan: str
    units_total: int
    units_used: int
    units_remaining: int
    period_start: datetime.datetime
    period_end: datetime.datetime
    limits: dict[str, int]
    billing_enabled: bool


class CheckoutIn(BaseModel):
    plan: str
    currency: str
    country: str


class UrlOut(BaseModel):
    url: str


class PlanOut(BaseModel):
    key: str
    prices: dict[str, int | None]
    price_label: str | None
    units: int
    max_agents: int
    max_rounds: int


class SubscriptionOut(BaseModel):
    status: str
    plan: str
    currency: str | None
    current_period_end: datetime.datetime | None
    cancel_at_period_end: bool


@router.get("/plans", response_model=list[PlanOut])
async def plans() -> list[PlanOut]:
    """The public rate card; the client renders these values, not its own."""
    settings = get_settings()
    rows: list[PlanOut] = []
    for key in ("starter", "studio", "enterprise"):
        plan = get_plan(key)
        rows.append(
            PlanOut(
                key=key,
                prices={currency: plan.prices.get(currency) for currency in SUPPORTED_CURRENCIES},
                price_label=(
                    settings.plan_enterprise_price_label if key == "enterprise" else None
                ),
                units=plan.units,
                max_agents=plan.max_agents,
                max_rounds=plan.max_rounds,
            )
        )
    return rows


@router.get("/usage", response_model=UsageOut)
async def usage(
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> UsageOut:
    entitlements = await resolve_entitlements(db, user=user)
    response.headers["Cache-Control"] = "private, no-store"
    return UsageOut(
        plan=entitlements.plan.key,
        units_total=entitlements.plan.units,
        units_used=entitlements.units_used,
        units_remaining=entitlements.units_remaining,
        period_start=entitlements.period_start,
        period_end=entitlements.period_end,
        limits={
            "max_agents": entitlements.plan.max_agents,
            "max_rounds": entitlements.plan.max_rounds,
        },
        billing_enabled=get_settings().billing_enabled,
    )


async def _latest_subscription(db: AsyncSession, user: User) -> Subscription | None:
    return (
        await db.execute(
            select(Subscription)
            .where(Subscription.user_id == user.id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _subscription_out(row: Subscription) -> SubscriptionOut:
    plan = plan_for_razorpay_plan(row.razorpay_plan_id)
    return SubscriptionOut(
        status=row.status,
        plan=plan.key if plan is not None else "free",
        currency=row.currency,
        current_period_end=row.current_period_end,
        cancel_at_period_end=row.cancel_at_period_end,
    )


@router.post(
    "/checkout", response_model=UrlOut, dependencies=[Depends(verify_csrf)]
)
async def checkout(
    body: CheckoutIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> UrlOut:
    if not razorpay_client.billing_configured():
        raise _service_unavailable()

    if body.plan not in PAID_PLANS:
        raise _validation_error("Unknown plan.")
    if body.currency not in SUPPORTED_CURRENCIES:
        raise _validation_error("Unsupported currency.")
    if not _COUNTRY_CODE.fullmatch(body.country):
        raise _validation_error("Country must be a two-letter ISO code.")

    plan = get_plan(body.plan)
    plan_id = plan.razorpay_plan_ids.get(body.currency)
    if plan_id is None:
        raise _validation_error("This plan is not available in that currency.")

    # Held through the Razorpay call (bounded by its timeout) so two concurrent
    # checkouts cannot both pass the blocking check below.
    await db.execute(select(User).where(User.id == user.id).with_for_update())

    blocking = (
        await db.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user.id,
                Subscription.status.in_(webhook_events.BLOCKING_SUBSCRIPTION_STATUSES),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if blocking is not None:
        if blocking.cancel_at_period_end:
            message = "Your current plan is set to end. You can subscribe again once it ends."
        else:
            message = "You already have a plan that is active or pending."
        raise HTTPException(
            status_code=409,
            detail={"code": "already_subscribed", "message": message},
        )

    settings = get_settings()
    try:
        created = await asyncio.to_thread(
            razorpay_client.create_subscription,
            plan_id=plan_id,
            user_id=str(user.id),
            plan_key=plan.key,
            currency=body.currency,
            country=body.country,
            total_count=settings.razorpay_subscription_total_count,
        )
    except razorpay_client.BillingNotConfigured as exc:
        raise _service_unavailable() from exc
    except razorpay_client.PROVIDER_ERRORS as exc:
        raise _upstream_error() from exc

    # Persisted before the URL check: a subscription the provider already holds
    # must stay visible to cancel and reconcile even if the user never gets a link.
    db.add(
        Subscription(
            user_id=user.id,
            razorpay_subscription_id=created["id"],
            razorpay_plan_id=plan_id,
            status=created["status"],
            currency=body.currency,
            billing_country=body.country,
            tax_amount=tax_amount_minor(
                plan_price_minor(plan, body.currency), body.country
            ),
        )
    )
    await db.commit()

    if not created.get("short_url"):
        raise _upstream_error()
    return UrlOut(url=created["short_url"])


@router.get("/subscription", response_model=SubscriptionOut | None)
async def subscription(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionOut | None:
    row = await _latest_subscription(db, user)
    return _subscription_out(row) if row is not None else None


@router.post(
    "/subscription/cancel",
    response_model=SubscriptionOut,
    dependencies=[Depends(verify_csrf)],
)
async def cancel_subscription(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionOut:
    if not razorpay_client.billing_configured():
        raise _service_unavailable()

    row = (
        await db.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user.id,
                Subscription.status.in_(webhook_events.OPEN_SUBSCRIPTION_STATUSES),
            )
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "No plan to cancel."},
        )

    # An active plan runs to the end of the period it has paid for; anything
    # not yet active has nothing to run out, so it is cancelled now.
    at_cycle_end = row.status == "active"
    try:
        await asyncio.to_thread(
            razorpay_client.cancel_subscription,
            row.razorpay_subscription_id,
            at_cycle_end=at_cycle_end,
        )
    except razorpay_client.BillingNotConfigured as exc:
        raise _service_unavailable() from exc
    except razorpay_client.PROVIDER_ERRORS as exc:
        raise _upstream_error() from exc

    row.cancel_at_period_end = at_cycle_end
    if not at_cycle_end:
        row.status = "cancelled"
    await db.commit()
    return _subscription_out(row)


@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Verify, record idempotently, and hand off processing — never on this path."""
    settings = get_settings()
    if not settings.razorpay_webhook_secret:
        # Fail closed: an empty HMAC key would let anyone forge events. Billing
        # off without a secret is the only way to reach this.
        raise _service_unavailable()

    raw_body = await request.body()
    try:
        razorpay_client.verify_webhook_signature(
            raw_body,
            request.headers.get("X-Razorpay-Signature"),
            secret=settings.razorpay_webhook_secret,
        )
    except Exception as exc:
        logger.warning("rejected Razorpay webhook: %s", exc)
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_signature", "message": "Invalid signature."},
        ) from exc

    event_id = request.headers.get("X-Razorpay-Event-Id")
    if not event_id:
        raise HTTPException(
            status_code=400,
            detail={"code": "missing_event_id", "message": "Missing event id."},
        )
    try:
        event = json.loads(raw_body)
        event_type = event["event"]
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_payload", "message": "Invalid payload."},
        ) from exc

    payload_hash = hashlib.sha256(raw_body).hexdigest()
    inserted = await webhook_events.store_event(
        db,
        provider_event_id=event_id,
        event_type=event_type,
        payload_hash=payload_hash,
        payload=event,
    )
    if not inserted:
        return {"received": True}

    row_id = (
        await db.execute(
            select(WebhookEvent.id).where(WebhookEvent.provider_event_id == event_id)
        )
    ).scalar_one()

    from rq import Retry

    from src.jobs import queue as jobs_queue
    from src.jobs import tasks

    try:
        if settings.queue_mode == "rq":
            jobs_queue.get_queue().enqueue(
                tasks.process_razorpay_event,
                str(row_id),
                retry=Retry(
                    max=settings.job_retry_max,
                    interval=list(settings.job_retry_intervals),
                ),
            )
        else:
            asyncio.create_task(tasks.process_razorpay_event_core(str(row_id)))
    except Exception as exc:
        # The event is recorded; a dispatch failure must not turn into a Razorpay
        # retry loop. It stays `pending` for an operator replay.
        logger.error("could not dispatch webhook event %s: %s", event_id, exc)

    return {"received": True}
