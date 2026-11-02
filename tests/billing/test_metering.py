"""Live tests for LLM token/cost metering — real Postgres, no mocked ledger."""

import datetime
import os
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select

from src.billing import metering
from src.billing.metering import (
    MeteringError,
    check_metering,
    metering_failed,
    metering_scope,
    record_llama_response,
    record_response,
    source_scope,
)
from src.billing.units import (
    get_balance,
    resolve_period,
    settle_call,
    units_for_tokens,
)
from src.db.engine import get_session_factory
from src.db.models import LLMUsage, Subscription, UsageEvent, UsagePeriod, User

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)


def _response(prompt=1500, completion=500, model="served-model", cost=0.0012):
    return SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion),
        model=model,
        _hidden_params={"response_cost": cost},
    )


async def _make_user(factory) -> uuid.UUID:
    async with factory() as db:
        user = User(
            email=f"metering-{uuid.uuid4()}@example.com", password_hash="$2b$12$meter"
        )
        db.add(user)
        await db.flush()
        user_id = user.id
        await db.commit()
    return user_id


async def _period(factory, user_id: uuid.UUID) -> datetime.datetime:
    async with factory() as db:
        start, _ = await resolve_period(db, user_id)
    return start


async def _cleanup(factory, user_id: uuid.UUID) -> None:
    async with factory() as db:
        await db.execute(delete(UsageEvent).where(UsageEvent.user_id == user_id))
        await db.execute(delete(LLMUsage).where(LLMUsage.user_id == user_id))
        await db.execute(delete(Subscription).where(Subscription.user_id == user_id))
        await db.execute(delete(UsagePeriod).where(UsagePeriod.user_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


async def _balance(factory, user_id: uuid.UUID, period_start: datetime.datetime):
    async with factory() as db:
        return await get_balance(db, user_id, period_start)


@pytest.mark.asyncio
async def test_no_context_does_no_db_work(monkeypatch):
    def _explode():
        raise AssertionError("no-context metering must not touch the database")

    monkeypatch.setattr(metering, "get_session_factory", _explode)
    await record_response(_response(), provider="openai")


@pytest.mark.asyncio
async def test_measured_call_writes_usage_and_settles_units(session_factory):
    factory = session_factory
    user_id = await _make_user(factory)
    try:
        period_start = await _period(factory, user_id)
        with metering_scope(
            user_id=user_id,
            period_start=period_start,
            source="debate",
            job_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
        ):
            await record_response(
                _response(), provider="openai", fallback_model="ignored"
            )

        async with factory() as db:
            usage = (
                await db.execute(select(LLMUsage).where(LLMUsage.user_id == user_id))
            ).scalar_one()
            event = (
                await db.execute(select(UsageEvent).where(UsageEvent.user_id == user_id))
            ).scalar_one()

        assert (usage.provider, usage.model) == ("openai", "served-model")
        assert (usage.prompt_tokens, usage.completion_tokens) == (1500, 500)
        assert usage.cost_usd == pytest.approx(0.0012)
        assert usage.call_id
        assert (event.amount, event.source) == (2, "debate")
        assert event.idempotency_key == usage.call_id

        used, _ = await _balance(factory, user_id, period_start)
        assert used == 2
    finally:
        await _cleanup(factory, user_id)


@pytest.mark.asyncio
async def test_source_scope_overrides_the_event_source(session_factory):
    factory = session_factory
    user_id = await _make_user(factory)
    try:
        period_start = await _period(factory, user_id)
        with metering_scope(
            user_id=user_id, period_start=period_start, source="debate"
        ):
            with source_scope("verdict"):
                await record_response(_response(), provider="anthropic")

        async with factory() as db:
            event = (
                await db.execute(select(UsageEvent).where(UsageEvent.user_id == user_id))
            ).scalar_one()
        assert event.source == "verdict"
    finally:
        await _cleanup(factory, user_id)


@pytest.mark.asyncio
async def test_settle_is_idempotent_by_call_id(session_factory):
    factory = session_factory
    user_id = await _make_user(factory)
    try:
        period_start = await _period(factory, user_id)
        with metering_scope(
            user_id=user_id, period_start=period_start, source="debate"
        ):
            await record_response(_response(), provider="openai")

        async with factory() as db:
            usage = (
                await db.execute(select(LLMUsage).where(LLMUsage.user_id == user_id))
            ).scalar_one()
            await settle_call(
                db,
                user_id=user_id,
                period_start=period_start,
                source="debate",
                amount=2,
                idempotency_key=usage.call_id,
            )

        async with factory() as db:
            events = (
                (
                    await db.execute(
                        select(UsageEvent).where(UsageEvent.user_id == user_id)
                    )
                )
                .scalars()
                .all()
            )
        used, _ = await _balance(factory, user_id, period_start)
        assert len(events) == 1
        assert used == 2
    finally:
        await _cleanup(factory, user_id)


@pytest.mark.asyncio
async def test_missing_usage_fails_closed_without_rows(session_factory):
    factory = session_factory
    user_id = await _make_user(factory)
    try:
        period_start = await _period(factory, user_id)
        with metering_scope(
            user_id=user_id, period_start=period_start, source="debate"
        ):
            await record_response(
                SimpleNamespace(usage=None, model="m"), provider="openai"
            )
            assert metering_failed() is True
            with pytest.raises(MeteringError):
                check_metering()

        async with factory() as db:
            assert (
                await db.execute(select(LLMUsage).where(LLMUsage.user_id == user_id))
            ).first() is None
            assert (
                await db.execute(select(UsageEvent).where(UsageEvent.user_id == user_id))
            ).first() is None
    finally:
        await _cleanup(factory, user_id)


@pytest.mark.asyncio
async def test_db_failure_does_not_raise_and_fails_closed(monkeypatch):
    def _explode():
        raise RuntimeError("db down")

    monkeypatch.setattr(metering, "get_session_factory", _explode)
    with metering_scope(
        user_id=uuid.uuid4(),
        period_start=datetime.datetime.now(datetime.UTC),
        source="debate",
    ):
        await record_response(_response(), provider="openai")
        assert metering_failed() is True
        with pytest.raises(MeteringError):
            check_metering()


@pytest.mark.asyncio
async def test_llama_response_is_metered_from_raw_usage(session_factory):
    factory = session_factory
    user_id = await _make_user(factory)
    try:
        period_start = await _period(factory, user_id)
        llama_response = SimpleNamespace(
            raw=SimpleNamespace(
                usage=SimpleNamespace(prompt_tokens=1500, completion_tokens=500),
                model="served",
            )
        )
        with metering_scope(
            user_id=user_id, period_start=period_start, source="ontology"
        ):
            await record_llama_response(llama_response, provider="openai")

        async with factory() as db:
            usage = (
                await db.execute(select(LLMUsage).where(LLMUsage.user_id == user_id))
            ).scalar_one()
            event = (
                await db.execute(select(UsageEvent).where(UsageEvent.user_id == user_id))
            ).scalar_one()

        assert (usage.provider, usage.model) == ("openai", "served")
        assert (usage.prompt_tokens, usage.completion_tokens) == (1500, 500)
        assert usage.cost_usd is None
        assert (event.amount, event.source) == (2, "ontology")
        assert event.idempotency_key == usage.call_id
    finally:
        await _cleanup(factory, user_id)


@pytest.mark.asyncio
async def test_llama_response_falls_back_to_additional_kwargs(session_factory):
    factory = session_factory
    user_id = await _make_user(factory)
    try:
        period_start = await _period(factory, user_id)
        llama_response = SimpleNamespace(
            raw=None,
            additional_kwargs={"prompt_tokens": 1, "completion_tokens": 0},
        )
        with metering_scope(
            user_id=user_id, period_start=period_start, source="ontology"
        ):
            await record_llama_response(
                llama_response, provider="openai", model="requested"
            )

        async with factory() as db:
            usage = (
                await db.execute(select(LLMUsage).where(LLMUsage.user_id == user_id))
            ).scalar_one()
            event = (
                await db.execute(select(UsageEvent).where(UsageEvent.user_id == user_id))
            ).scalar_one()
        assert usage.model == "requested"
        assert event.amount == 1
    finally:
        await _cleanup(factory, user_id)


@pytest.mark.asyncio
async def test_llama_missing_usage_fails_closed():
    with metering_scope(
        user_id=uuid.uuid4(),
        period_start=datetime.datetime.now(datetime.UTC),
        source="ontology",
    ):
        await record_llama_response(
            SimpleNamespace(raw=None, additional_kwargs={}), provider="openai"
        )
        assert metering_failed() is True
        with pytest.raises(MeteringError):
            check_metering()


def test_units_math():
    assert units_for_tokens(0, 0) == 0
    assert units_for_tokens(1, 0) == 1
    assert units_for_tokens(1_000, 0) == 1
    assert units_for_tokens(1_000, 1) == 2
