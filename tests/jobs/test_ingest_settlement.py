"""Ingest settlement: measured chars, sha256 dedupe, and release on every exit."""

import asyncio
import datetime
import json
import os
import sys
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select

from src.api import run_doc
from src.billing import units
from src.db.engine import get_session_factory
from src.db.models import Job, LLMUsage, Upload, UsageEvent, User
from src.jobs import tasks

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)
pytestmark = [requires_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def owner(db):
    factory = get_session_factory()
    async with factory() as session:
        user = User(
            email=f"auth-test-ingest-settle-{uuid.uuid4().hex[:10]}@example.com",
            password_hash="not-a-real-hash",
        )
        session.add(user)
        await session.commit()
        user_id = user.id
    try:
        yield user_id
    finally:
        async with factory() as session:
            # usage_events/llm_usage outlive the user row (FK SET NULL).
            await session.execute(
                delete(UsageEvent).where(UsageEvent.user_id == user_id)
            )
            await session.execute(delete(LLMUsage).where(LLMUsage.user_id == user_id))
            await session.commit()


async def _seed_upload(
    owner: uuid.UUID,
    *,
    sha256: str,
    text: str | None = None,
    created_at: datetime.datetime | None = None,
) -> str:
    upload_id = uuid.uuid4()
    factory = get_session_factory()
    async with factory() as session:
        row = Upload(
            id=upload_id,
            user_id=owner,
            object_key=f"{owner}/{upload_id}",
            name="notes.txt",
            bytes=10,
            mime="text/plain",
            sha256=sha256,
            extracted_text=text,
        )
        if created_at is not None:
            row.created_at = created_at
        session.add(row)
        await session.commit()
    return str(upload_id)


async def _get_upload(upload_id: str) -> Upload | None:
    factory = get_session_factory()
    async with factory() as session:
        return await session.get(Upload, uuid.UUID(upload_id))


async def _period(owner: uuid.UUID) -> datetime.datetime:
    factory = get_session_factory()
    async with factory() as session:
        period_start, _ = await units.resolve_period(session, owner)
    return period_start


async def _balance(
    owner: uuid.UUID, period_start: datetime.datetime
) -> tuple[int, int]:
    factory = get_session_factory()
    async with factory() as session:
        return await units.get_balance(session, owner, period_start)


async def _events(owner: uuid.UUID) -> list[UsageEvent]:
    factory = get_session_factory()
    async with factory() as session:
        rows = await session.execute(
            select(UsageEvent)
            .where(UsageEvent.user_id == owner)
            .order_by(UsageEvent.created_at)
        )
        return list(rows.scalars().all())


async def _llm_usage_count(owner: uuid.UUID) -> int:
    factory = get_session_factory()
    async with factory() as session:
        return (
            await session.execute(
                select(func.count())
                .select_from(LLMUsage)
                .where(LLMUsage.user_id == owner)
            )
        ).scalar_one()


async def _job_row(job_id: str) -> Job | None:
    factory = get_session_factory()
    async with factory() as session:
        return await session.get(Job, uuid.UUID(job_id))


async def _reserve_job(
    owner: uuid.UUID, job_id: str, estimate: int = 3
) -> datetime.datetime:
    factory = get_session_factory()
    async with factory() as session:
        reservation = await units.reserve_units(
            session, user_id=owner, plan_key="free", estimate=estimate
        )
    await run_doc.write_job_doc(
        {
            "job_id": job_id,
            "user_id": str(owner),
            "mode": "extract_upload",
            "status": "queued",
            "progress": 0.0,
            "stage": "queued",
            "error": None,
            "result": None,
            "reserved_units": reservation.amount,
            "reserved_period_start": reservation.period_start.isoformat(),
            "reserved_at": datetime.datetime.now(datetime.UTC).isoformat(),
        }
    )
    return reservation.period_start


async def test_a_duplicate_sha256_copies_text_and_settles_zero(owner, monkeypatch):
    sha = uuid.uuid4().hex
    prior_text = json.dumps({"document_id": "prior", "text": "already extracted"})
    now = datetime.datetime.now(datetime.UTC)
    await _seed_upload(
        owner,
        sha256=sha,
        text=prior_text,
        created_at=now - datetime.timedelta(minutes=1),
    )
    current_id = await _seed_upload(owner, sha256=sha, created_at=now)

    def explode(*_args, **_kwargs):
        raise AssertionError("a duplicate must not be read or extracted")

    monkeypatch.setattr("src.jobs.tasks._read_object", explode)
    monkeypatch.setattr("src.ingest.bounded.run_extraction", explode)

    await tasks._extract_file_upload(
        str(owner),
        current_id,
        "notes.txt",
        10,
        1_000_000,
        await _period(owner),
        str(uuid.uuid4()),
    )

    row = await _get_upload(current_id)
    assert row.extracted_text == prior_text

    events = await _events(owner)
    assert len(events) == 1
    assert (events[0].source, events[0].amount) == ("ingest", 0)
    assert events[0].reason == "duplicate sha256"
    assert await _llm_usage_count(owner) == 0


async def test_first_extraction_settles_the_measured_chars(owner, monkeypatch):
    upload_id = await _seed_upload(owner, sha256=uuid.uuid4().hex)
    period_start = await _period(owner)
    job_id = str(uuid.uuid4())
    await run_doc.write_job_doc(
        {
            "job_id": job_id,
            "user_id": str(owner),
            "mode": "extract_upload",
            "status": "queued",
            "progress": 0.0,
            "stage": "queued",
            "error": None,
            "result": None,
            "reserved_units": 3,
            "reserved_period_start": period_start.isoformat(),
            "reserved_at": datetime.datetime.now(datetime.UTC).isoformat(),
        }
    )
    document = {
        "document_id": uuid.uuid4().hex,
        "title": "notes.txt",
        "text": "x" * 4000,
        "word_count": 4000,
        "source_type": "file",
        "mime_type": "text/plain",
    }
    monkeypatch.setattr("src.jobs.tasks._read_object", lambda _key: b"hello text")
    monkeypatch.setattr(
        "src.ingest.bounded.run_extraction", lambda *_a, **_k: {"document": document}
    )

    await tasks._extract_file_upload(
        str(owner), upload_id, "notes.txt", 10, 1_000_000, period_start, job_id
    )

    events = await _events(owner)
    assert len(events) == 1
    assert events[0].source == "ingest"
    assert events[0].amount == 2
    assert events[0].idempotency_key == f"ingest:{upload_id}"

    job = await _job_row(job_id)
    assert job.reserved_units == 1  # 3 reserved, 2 settled


async def test_execute_releases_the_ingest_hold_on_success(owner, monkeypatch):
    job_id = str(uuid.uuid4())
    period_start = await _reserve_job(owner, job_id)

    async def core(_job_id, _payload):
        return None

    monkeypatch.setitem(tasks.CORES, "extract_upload", core)
    await tasks.execute(
        "extract_upload", job_id, {"user_id": str(owner), "upload_ids": []}
    )

    job = await _job_row(job_id)
    assert job.status == "completed"
    assert job.reserved_units == 0
    assert await _balance(owner, period_start) == (0, 0)


async def test_execute_releases_the_ingest_hold_on_failure(owner, monkeypatch):
    job_id = str(uuid.uuid4())
    period_start = await _reserve_job(owner, job_id)

    async def core(_job_id, _payload):
        raise RuntimeError("extractor crashed")

    monkeypatch.setitem(tasks.CORES, "extract_upload", core)
    with pytest.raises(RuntimeError, match="extractor crashed"):
        await tasks.execute(
            "extract_upload", job_id, {"user_id": str(owner), "upload_ids": []}
        )

    job = await _job_row(job_id)
    assert job.status == "failed"
    assert job.reserved_units == 0
    assert await _balance(owner, period_start) == (0, 0)
