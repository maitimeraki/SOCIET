"""Capture LiteLLM usage per call and settle the measured units (ledger R9, R20).

``record_response`` writes one ``llm_usage`` row and one ``usage_events`` row for
every call made inside a ``metering_scope``. A failure never raises out of a
served call: it flags the context, and the next call's ``check_metering`` stops
the job before it spends again. Calls made with no context (boot probes, unit
tests) are not metered.
"""

import contextvars
import datetime
import logging
import uuid
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass

from src.billing.units import (
    SOURCES,
    get_balance,
    settle_call,
    units_for_tokens,
)
from src.db.engine import get_session_factory
from src.db.models import LLMUsage

logger = logging.getLogger(__name__)


class MeteringError(RuntimeError):
    """Accounting already failed; the job must stop before its next call."""


@dataclass
class MeteringContext:
    user_id: uuid.UUID
    period_start: datetime.datetime
    source: str
    job_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    plan_units: int | None = None
    failed: bool = False
    failure_reason: str | None = None


_context: contextvars.ContextVar[MeteringContext | None] = contextvars.ContextVar(
    "llm_metering_context", default=None
)
# Separate from the context so a nested override neither drops the failure flag
# nor is lost when a parallel call mutates the shared context object.
_source_override: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "llm_metering_source", default=None
)


def _as_uuid(value: uuid.UUID | str) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _optional_uuid(value: uuid.UUID | str | None) -> uuid.UUID | None:
    return None if value is None else _as_uuid(value)


def _validate_source(source: str) -> None:
    if source not in SOURCES:
        raise ValueError(f"source must be one of {sorted(SOURCES)}")


@contextmanager
def metering_scope(
    *,
    user_id: uuid.UUID | str,
    period_start: datetime.datetime,
    source: str,
    job_id: uuid.UUID | str | None = None,
    run_id: uuid.UUID | str | None = None,
    plan_units: int | None = None,
):
    _validate_source(source)
    context = MeteringContext(
        user_id=_as_uuid(user_id),
        period_start=period_start,
        source=source,
        job_id=_optional_uuid(job_id),
        run_id=_optional_uuid(run_id),
        plan_units=plan_units,
    )
    token = _context.set(context)
    try:
        yield context
    finally:
        _context.reset(token)


@contextmanager
def source_scope(source: str):
    _validate_source(source)
    token = _source_override.set(source)
    try:
        yield
    finally:
        _source_override.reset(token)


def current_context() -> MeteringContext | None:
    return _context.get()


def metering_failed() -> bool:
    context = _context.get()
    return context is not None and context.failed


def check_metering() -> None:
    context = _context.get()
    if context is not None and context.failed:
        raise MeteringError(f"metering failed: {context.failure_reason}")


def _fail(context: MeteringContext, reason: str) -> None:
    if not context.failed:
        context.failed = True
        context.failure_reason = reason


def _usage_field(usage: object, name: str) -> object:
    if isinstance(usage, Mapping):
        return usage.get(name)
    return getattr(usage, name, None)


def _token_count(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _missing_usage(context: MeteringContext, provider: str) -> None:
    _fail(context, "usage missing")
    logger.error(
        "LLM call (%s) returned no measured usage; metering failed, the next "
        "call will stop the job",
        provider,
    )


async def _write_usage(
    context: MeteringContext,
    *,
    source: str,
    provider: str,
    model: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    cost: float | None,
) -> None:
    """The one write path: one llm_usage row, one settled usage event."""
    amount = units_for_tokens(prompt_tokens, completion_tokens)
    call_id = str(uuid.uuid4())

    try:
        async with get_session_factory()() as db:
            try:
                db.add(
                    LLMUsage(
                        user_id=context.user_id,
                        run_id=context.run_id,
                        job_id=context.job_id,
                        call_id=call_id,
                        source=source,
                        provider=provider,
                        model=model,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        cost_usd=cost,
                    )
                )
                await settle_call(
                    db,
                    user_id=context.user_id,
                    period_start=context.period_start,
                    source=source,
                    amount=amount,
                    idempotency_key=call_id,
                )
                if context.plan_units is not None:
                    units_used, _ = await get_balance(
                        db, context.user_id, context.period_start
                    )
                    if units_used >= context.plan_units:
                        _fail(context, "balance exhausted")
            except Exception:
                await db.rollback()
                raise
    except Exception as exc:
        _fail(context, str(exc) or exc.__class__.__name__)
        logger.exception(
            "could not settle LLM usage (%s, source=%s); metering failed, the "
            "next call will stop the job",
            provider,
            source,
        )
        return


async def record_response(
    response: object,
    *,
    provider: str,
    fallback_model: str | None = None,
) -> None:
    """Meter a LiteLLM completion (``response.usage`` + ``_hidden_params``)."""
    context = _context.get()
    if context is None:
        return
    source = _source_override.get() or context.source
    _validate_source(source)

    usage = getattr(response, "usage", None)
    prompt_tokens = _token_count(_usage_field(usage, "prompt_tokens")) if usage else None
    completion_tokens = (
        _token_count(_usage_field(usage, "completion_tokens")) if usage else None
    )
    if prompt_tokens is None or completion_tokens is None:
        _missing_usage(context, provider)
        return

    model = getattr(response, "model", None) or fallback_model
    hidden = getattr(response, "_hidden_params", None)
    cost = hidden.get("response_cost") if isinstance(hidden, Mapping) else None
    await _write_usage(
        context,
        source=source,
        provider=provider,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost=cost,
    )


async def record_llama_response(
    response: object,
    *,
    provider: str,
    model: str | None = None,
) -> None:
    """Meter a llama-index response (graph stages bypass ``LLMClient``).

    Token counts come from ``response.raw.usage``; llama-index's
    ``_get_response_token_counts`` fallback lands in ``additional_kwargs``.
    OpenAILike exposes no litellm ``response_cost``, so cost is never invented.
    """
    context = _context.get()
    if context is None:
        return
    source = _source_override.get() or context.source
    _validate_source(source)

    raw = getattr(response, "raw", None)
    usage = getattr(raw, "usage", None)
    prompt_tokens = _token_count(_usage_field(usage, "prompt_tokens")) if usage else None
    completion_tokens = (
        _token_count(_usage_field(usage, "completion_tokens")) if usage else None
    )
    extra = getattr(response, "additional_kwargs", None)
    if isinstance(extra, Mapping):
        if prompt_tokens is None:
            prompt_tokens = _token_count(extra.get("prompt_tokens"))
        if completion_tokens is None:
            completion_tokens = _token_count(extra.get("completion_tokens"))
    if prompt_tokens is None or completion_tokens is None:
        _missing_usage(context, provider)
        return

    await _write_usage(
        context,
        source=source,
        provider=provider,
        model=getattr(raw, "model", None) or model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost=None,
    )
