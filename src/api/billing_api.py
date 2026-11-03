"""Billing HTTP surface: usage read, hosted Checkout, Customer Portal, webhook.

The webhook sits under ``/api/`` with no CSRF dependency and no
``service_available`` gate — payment must keep working while the LLM is down.
Checkout and portal are state-changing user actions and do carry CSRF.
"""

import asyncio
import datetime
import hashlib
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.cookies import verify_csrf
from src.auth.deps import current_user
from src.billing import stripe_client
from src.billing import webhook as webhook_events
from src.billing.entitlements import resolve_entitlements
from src.billing.plans import get_plan
from src.config.settings import get_settings
from src.db.engine import get_db
from src.db.models import Subscription, User, WebhookEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


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


def _raise_upstream_if_stripe(exc: Exception) -> None:
    import stripe

    if isinstance(exc, stripe.error.StripeError):
        raise _upstream_error() from exc


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


class UrlOut(BaseModel):
    url: str


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


async def _customer_for_user(
    db: AsyncSession, user: User
) -> str:
    """The user's Stripe customer id, creating the customer + mirror on first use."""
    row = (
        await db.execute(
            select(Subscription)
            .where(Subscription.user_id == user.id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is not None and row.stripe_customer_id:
        return row.stripe_customer_id

    customer = stripe_client.create_customer(email=user.email, user_id=str(user.id))
    customer_id = customer["id"]
    if row is None:
        db.add(
            Subscription(
                user_id=user.id,
                stripe_customer_id=customer_id,
                status="incomplete",
            )
        )
    else:
        row.stripe_customer_id = customer_id
    await db.commit()
    return customer_id


@router.post(
    "/checkout", response_model=UrlOut, dependencies=[Depends(verify_csrf)]
)
async def checkout(
    body: CheckoutIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> UrlOut:
    if not stripe_client.billing_configured():
        raise _service_unavailable()

    plan = get_plan(body.plan)
    if body.plan not in ("starter", "studio") or plan.stripe_price_id is None:
        raise HTTPException(
            status_code=422,
            detail={"code": "validation_error", "message": "Unknown plan."},
        )

    settings = get_settings()
    try:
        customer_id = await _customer_for_user(db, user)
        session = stripe_client.create_checkout_session(
            customer_id=customer_id,
            price_id=plan.stripe_price_id,
            user_id=str(user.id),
            plan=plan.key,
            success_url=f"{settings.app_base_url}/pricing?checkout=success",
            cancel_url=f"{settings.app_base_url}/pricing?checkout=cancel",
        )
    except stripe_client.BillingNotConfigured as exc:
        raise _service_unavailable() from exc
    except Exception as exc:
        _raise_upstream_if_stripe(exc)
        raise

    return UrlOut(url=session["url"])


@router.post("/portal", response_model=UrlOut, dependencies=[Depends(verify_csrf)])
async def portal(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> UrlOut:
    if not stripe_client.billing_configured():
        raise _service_unavailable()

    row = (
        await db.execute(
            select(Subscription)
            .where(Subscription.user_id == user.id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None or not row.stripe_customer_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "No billing account."},
        )

    try:
        session = stripe_client.create_portal_session(
            customer_id=row.stripe_customer_id,
            return_url=f"{get_settings().app_base_url}/account",
        )
    except stripe_client.BillingNotConfigured as exc:
        raise _service_unavailable() from exc
    except Exception as exc:
        _raise_upstream_if_stripe(exc)
        raise

    return UrlOut(url=session["url"])


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Verify, record idempotently, and hand off processing — never on this path."""
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        # Fail closed: an empty HMAC key would let anyone forge events. Billing
        # off without a secret is the only way to reach this.
        raise _service_unavailable()

    raw_body = await request.body()
    try:
        webhook_events.verify_signature(
            raw_body,
            request.headers.get("Stripe-Signature"),
            secret=settings.stripe_webhook_secret,
            tolerance=settings.stripe_webhook_tolerance_seconds,
        )
        event = webhook_events.parse_event(raw_body)
    except Exception as exc:
        logger.warning("rejected Stripe webhook: %s", exc)
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_signature", "message": "Invalid signature."},
        ) from exc

    payload_hash = hashlib.sha256(raw_body).hexdigest()
    if not await webhook_events.store_event(db, event, payload_hash):
        return {"received": True}

    row_id = (
        await db.execute(
            select(WebhookEvent.id).where(
                WebhookEvent.provider_event_id == event["id"]
            )
        )
    ).scalar_one()

    from rq import Retry

    from src.jobs import queue as jobs_queue
    from src.jobs import tasks

    try:
        if settings.queue_mode == "rq":
            jobs_queue.get_queue().enqueue(
                tasks.process_stripe_event,
                str(row_id),
                retry=Retry(
                    max=settings.job_retry_max,
                    interval=list(settings.job_retry_intervals),
                ),
            )
        else:
            asyncio.create_task(tasks.process_stripe_event_core(str(row_id)))
    except Exception as exc:
        # The event is recorded; a dispatch failure must not turn into a Stripe
        # retry loop. It stays `pending` for an operator replay.
        logger.error("could not dispatch webhook event %s: %s", event["id"], exc)

    return {"received": True}
