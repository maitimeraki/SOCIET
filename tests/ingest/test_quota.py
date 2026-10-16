"""Per-user upload quota: SQL usage, rejection, and Retry-After semantics."""

import asyncio
import datetime
import os
import sys
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete

from src.db.engine import get_session_factory
from src.db.models import Upload, User
from src.ingest import quota
from src.ingest.quota import (
    QuotaExceeded,
    enforce_upload_quota,
    retry_after_seconds,
    usage_this_month,
)

if sys.platform == "win32":
    # psycopg refuses async on the default ProactorEventLoop (see conftest).
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)


# --- Retry-After is pure arithmetic — runs without a database. -------------


def test_retry_after_capped_at_24h():
    mid_month = datetime.datetime(2026, 10, 14, 12, 0, tzinfo=datetime.timezone.utc)
    assert retry_after_seconds(mid_month) == 86_400


def test_retry_after_counts_to_month_end():
    near_end = datetime.datetime(2026, 10, 31, 23, 0, tzinfo=datetime.timezone.utc)
    assert retry_after_seconds(near_end) == 3_600


def test_retry_after_floored_at_one():
    last_instant = datetime.datetime(
        2026, 10, 31, 23, 59, 59, 999_999, tzinfo=datetime.timezone.utc
    )
    assert retry_after_seconds(last_instant) == 1


# --- Enforcement is DB-backed. ---------------------------------------------


class _SmallQuota:
    upload_quota_bytes_month = 1_000
    upload_quota_files_month = 2


@pytest_asyncio.fixture
async def quota_user(db):
    factory = get_session_factory()
    async with factory() as session:
        user = User(
            email=f"quota-{uuid.uuid4().hex[:10]}@example.com",
            password_hash="not-a-real-hash",
        )
        session.add(user)
        await session.commit()
        user_id = user.id
    yield user_id
    async with factory() as session:
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


async def _add_upload(session, user_id, size, created_at=None):
    upload_id = uuid.uuid4()
    row = Upload(
        id=upload_id,
        user_id=user_id,
        object_key=f"{user_id}/{upload_id}",
        bytes=size,
        mime="application/pdf",
        sha256="0" * 64,
    )
    if created_at is not None:
        row.created_at = created_at
    session.add(row)
    await session.commit()


@requires_db
@pytest.mark.asyncio
async def test_under_quota_allowed(db, quota_user, monkeypatch):
    monkeypatch.setattr(quota, "get_settings", lambda: _SmallQuota())
    await _add_upload(db, quota_user, 500)
    await enforce_upload_quota(db, quota_user, incoming_bytes=400)  # 900 <= 1000


@requires_db
@pytest.mark.asyncio
async def test_over_bytes_rejected_with_retry_after(db, quota_user, monkeypatch):
    monkeypatch.setattr(quota, "get_settings", lambda: _SmallQuota())
    await _add_upload(db, quota_user, 500)
    with pytest.raises(QuotaExceeded) as exc:
        await enforce_upload_quota(db, quota_user, incoming_bytes=600)  # 1100 > 1000
    assert 1 <= exc.value.retry_after <= 86_400


@requires_db
@pytest.mark.asyncio
async def test_over_files_rejected(db, quota_user, monkeypatch):
    monkeypatch.setattr(quota, "get_settings", lambda: _SmallQuota())
    await _add_upload(db, quota_user, 1)
    await _add_upload(db, quota_user, 1)
    with pytest.raises(QuotaExceeded):
        await enforce_upload_quota(db, quota_user, incoming_files=1)  # 3 > 2


@requires_db
@pytest.mark.asyncio
async def test_usage_counts_only_current_month(db, quota_user):
    now = datetime.datetime.now(datetime.timezone.utc)
    previous_month = now.replace(day=1) - datetime.timedelta(days=1)
    await _add_upload(db, quota_user, 300, created_at=previous_month)
    await _add_upload(db, quota_user, 100)
    assert await usage_this_month(db, quota_user) == (100, 1)
