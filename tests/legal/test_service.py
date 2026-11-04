"""Seeded documents and append-only consent — live Postgres behavior."""

import asyncio
import datetime
import os
import sys
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select

from src.db.models import LegalDocument, User, UserConsent
from src.legal import registry
from src.legal.service import (
    current_documents,
    ensure_documents,
    has_accepted_current,
    record_consents,
)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)
pytestmark = [requires_db, pytest.mark.asyncio]


@pytest_asyncio.fixture(autouse=True)
async def _clean_legal(db):
    """The registry is global: start and end each test from empty tables."""
    await db.execute(delete(UserConsent))
    await db.execute(delete(LegalDocument))
    await db.commit()
    yield
    await db.execute(delete(UserConsent))
    await db.execute(delete(LegalDocument))
    await db.commit()


async def _make_user(db) -> uuid.UUID:
    user = User(
        email=f"auth-test-legal-{uuid.uuid4().hex[:10]}@example.com",
        password_hash="not-a-real-hash",
    )
    db.add(user)
    await db.flush()
    return user.id


async def _consent_count(db, user_id: uuid.UUID) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(UserConsent)
            .where(UserConsent.user_id == user_id)
        )
    ).scalar_one()


async def test_ensure_documents_inserts_four_rows_and_is_idempotent(db):
    rows = await ensure_documents(db, commit=True)

    assert len(rows) == 4
    assert {row.slug for row in rows} == {seed.slug for seed in registry.SEEDS}

    again = await ensure_documents(db, commit=True)
    assert {row.id for row in again} == {row.id for row in rows}

    total = (
        await db.execute(select(func.count()).select_from(LegalDocument))
    ).scalar_one()
    assert total == 4


async def test_concurrent_first_reads_do_not_raise(db):
    """Two first requests race the seed insert; ON CONFLICT makes both succeed."""
    from src.db.engine import get_session_factory

    factory = get_session_factory()

    async def _ensure():
        async with factory() as session:
            return await ensure_documents(session, commit=True)

    first, second = await asyncio.gather(_ensure(), _ensure())

    assert {row.id for row in first} == {row.id for row in second}
    assert len(first) == len(registry.SEEDS) == len(second)


async def test_changing_bytes_without_a_version_bump_raises(db, monkeypatch):
    await ensure_documents(db, commit=True)
    real_read = registry.read_raw

    def edited(seed):
        raw = real_read(seed)
        return raw + "\nchanged" if seed.slug == "terms" else raw

    monkeypatch.setattr(registry, "read_raw", edited)

    with pytest.raises(RuntimeError, match="without a version bump"):
        await ensure_documents(db)


async def test_current_documents_returns_one_row_per_slug_ordered(db):
    await ensure_documents(db, commit=True)
    db.add(
        LegalDocument(
            slug="privacy",
            version="2099-01-01",
            effective_at=datetime.datetime(2099, 1, 1, tzinfo=datetime.UTC),
            content_sha256="f" * 64,
            content="a newer privacy version",
        )
    )
    await db.commit()

    rows = await current_documents(db)

    assert [row.slug for row in rows] == [
        "privacy",
        "refund",
        "subprocessors",
        "terms",
    ]
    assert next(row for row in rows if row.slug == "privacy").version == "2099-01-01"


async def test_record_consents_inserts_two_rows_and_is_idempotent(db):
    user_id = await _make_user(db)

    accepted = await record_consents(
        db,
        user_id=user_id,
        ip="127.0.0.1",
        user_agent="pytest",
        commit=True,
    )

    assert accepted == ["terms", "privacy"]
    assert await _consent_count(db, user_id) == 2

    assert await record_consents(db, user_id=user_id, commit=True) == [
        "terms",
        "privacy",
    ]
    assert await _consent_count(db, user_id) == 2
    assert await has_accepted_current(db, user_id) is True


async def test_new_version_requires_fresh_consent(db, monkeypatch):
    user_id = await _make_user(db)
    await record_consents(db, user_id=user_id, commit=True)
    assert await has_accepted_current(db, user_id) is True

    newer_privacy = registry.LegalDocSeed(
        slug="privacy",
        version="2099-01-01",
        effective_at=datetime.date(2099, 1, 1),
        filename="privacy.md",
    )
    monkeypatch.setattr(registry, "SEEDS", registry.SEEDS + (newer_privacy,))

    assert await has_accepted_current(db, user_id) is False
