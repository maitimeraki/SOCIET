"""Retention purge (plan §12): each age window trims its own data; dry-run is a
pure read. Ages are derived from the settings so the test tracks the windows."""

import asyncio
import datetime
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select

from src.config.settings import get_settings
from src.db.engine import get_session_factory
from src.db.models import (
    AuditLog,
    Job,
    LLMUsage,
    Run,
    RunEvent,
    Upload,
    User,
    WebhookEvent,
)
from src.ingest import storage
from src.jobs import tasks

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)
pytestmark = [requires_db, pytest.mark.asyncio]

BUCKET = "societas-uploads"
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest_asyncio.fixture
async def owner(db):
    factory = get_session_factory()
    async with factory() as session:
        user = User(
            email=f"auth-test-retention-{uuid.uuid4().hex[:10]}@example.com",
            password_hash="not-a-real-hash",
        )
        session.add(user)
        await session.commit()
        return str(user.id)


@pytest.fixture
def s3(monkeypatch):
    moto = pytest.importorskip("moto")
    settings = SimpleNamespace(
        s3_endpoint_url=None,
        s3_access_key="testing",
        s3_secret_key="testing",
        s3_bucket=BUCKET,
        s3_region="us-east-1",
    )
    monkeypatch.setattr(storage, "get_settings", lambda: settings)
    with moto.mock_aws():
        storage._client.cache_clear()
        storage._client().create_bucket(Bucket=BUCKET)
        yield
    storage._client.cache_clear()


async def _seed(owner_id: str) -> dict[str, uuid.UUID]:
    """One past-window row and one fresh row per window, plus a URL upload row.

    A URL upload carries its source URL as ``object_key`` and has no stored
    object — the purge must leave it alone.
    """
    owner = uuid.UUID(owner_id)
    settings = get_settings()
    now = datetime.datetime.now(datetime.timezone.utc)
    old_run = now - datetime.timedelta(days=settings.retention_runs_days + 5)
    old_upload = now - datetime.timedelta(days=settings.retention_raw_uploads_days + 5)
    old_audit = now - datetime.timedelta(days=settings.retention_audit_days + 5)
    fresh = now - datetime.timedelta(days=1)

    ids = {
        "old_run": uuid.uuid4(),
        "new_run": uuid.uuid4(),
        "old_upload": uuid.uuid4(),
        "new_upload": uuid.uuid4(),
        "old_url_upload": uuid.uuid4(),
        "old_audit": uuid.uuid4(),
        "new_audit": uuid.uuid4(),
        "old_webhook": uuid.uuid4(),
        "new_webhook": uuid.uuid4(),
        "old_llm": uuid.uuid4(),
        "new_llm": uuid.uuid4(),
    }
    factory = get_session_factory()
    async with factory() as session:
        for run_id, created in ((ids["old_run"], old_run), (ids["new_run"], fresh)):
            session.add(
                Run(
                    id=run_id,
                    user_id=owner,
                    query="q",
                    status="complete",
                    created_at=created,
                )
            )
        await session.flush()  # runs before jobs (FK jobs.run_id → runs.id)
        for run_id, created in ((ids["old_run"], old_run), (ids["new_run"], fresh)):
            session.add(
                Job(
                    id=run_id,
                    user_id=owner,
                    run_id=run_id,
                    kind="debate",
                    status="complete",
                    queued_at=created,
                )
            )
        await session.flush()  # jobs before run_events
        for run_id, created in ((ids["old_run"], old_run), (ids["new_run"], fresh)):
            session.add(
                RunEvent(
                    id=uuid.uuid4(), run_id=run_id, seq=0, type="run_meta", at=created
                )
            )
        for upload_id, created, key in (
            (ids["old_upload"], old_upload, f"{owner}/{ids['old_upload']}"),
            (ids["new_upload"], fresh, f"{owner}/{ids['new_upload']}"),
            (ids["old_url_upload"], old_upload, "https://example.com/page"),
        ):
            session.add(
                Upload(
                    id=upload_id,
                    user_id=owner,
                    object_key=key,
                    bytes=4,
                    mime="text/plain",
                    sha256="sha",
                    created_at=created,
                )
            )
        for audit_id, at in ((ids["old_audit"], old_audit), (ids["new_audit"], fresh)):
            session.add(AuditLog(id=audit_id, action="login", at=at))
        for key, at in (("old_webhook", old_audit), ("new_webhook", fresh)):
            session.add(
                WebhookEvent(
                    id=ids[key],
                    provider_event_id=f"evt-{ids[key]}",
                    event_type="customer.updated",
                    payload_hash="h",
                    received_at=at,
                )
            )
        for key, at in (("old_llm", old_audit), ("new_llm", fresh)):
            session.add(
                LLMUsage(
                    id=ids[key],
                    call_id=str(ids[key]),
                    source="debate",
                    created_at=at,
                )
            )
        await session.commit()

    storage.put_upload(owner, ids["old_upload"], b"data")
    storage.put_upload(owner, ids["new_upload"], b"data")
    return ids


async def _exists(model, key: uuid.UUID) -> bool:
    factory = get_session_factory()
    async with factory() as session:
        return await session.get(model, key) is not None


async def _event_count(run_id: uuid.UUID) -> int:
    factory = get_session_factory()
    async with factory() as session:
        return (
            await session.execute(
                select(func.count())
                .select_from(RunEvent)
                .where(RunEvent.run_id == run_id)
            )
        ).scalar_one()


async def _cleanup_audit(*audit_ids: uuid.UUID) -> None:
    """audit_log.user_id is SET NULL on user delete, so the db fixture cannot
    sweep these rows — remove them here."""
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(delete(AuditLog).where(AuditLog.id.in_(audit_ids)))
        await session.commit()


async def _cleanup_rows(model, *keys: uuid.UUID) -> None:
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(delete(model).where(model.id.in_(keys)))
        await session.commit()


def _object_bytes(key: str) -> bytes:
    with storage.get_upload(key) as body:
        return body.read()


async def test_each_window_purges_its_old_rows_and_keeps_the_fresh_ones(owner, s3):
    ids = await _seed(owner)

    counts = await tasks.purge_retention_core(dry_run=False)

    assert counts["runs"] >= 1
    assert counts["raw_objects"] >= 1
    assert counts["audit"] >= 1
    assert counts["webhook_events"] >= 1
    assert counts["llm_usage"] >= 1

    # Runs older than the window are gone in full: run + job + event.
    assert not await _exists(Run, ids["old_run"])
    assert not await _exists(Job, ids["old_run"])
    assert await _event_count(ids["old_run"]) == 0
    # Fresh runs survive.
    assert await _exists(Run, ids["new_run"])
    assert await _exists(Job, ids["new_run"])

    # Raw upload: the OBJECT is gone, the ROW (metadata + extracted text) stays.
    assert await _exists(Upload, ids["old_upload"])
    with pytest.raises(Exception):
        storage.get_upload(f"{owner}/{ids['old_upload']}")
    # A fresh upload keeps both.
    assert await _exists(Upload, ids["new_upload"])
    assert _object_bytes(f"{owner}/{ids['new_upload']}") == b"data"
    # A URL upload has no object; the row is left alone.
    assert await _exists(Upload, ids["old_url_upload"])

    # Audit is trimmed to its window.
    assert not await _exists(AuditLog, ids["old_audit"])
    assert await _exists(AuditLog, ids["new_audit"])

    # Webhook payloads and LLM usage age out on the same runs window.
    assert not await _exists(WebhookEvent, ids["old_webhook"])
    assert await _exists(WebhookEvent, ids["new_webhook"])
    assert not await _exists(LLMUsage, ids["old_llm"])
    assert await _exists(LLMUsage, ids["new_llm"])

    await _cleanup_audit(ids["new_audit"])
    await _cleanup_rows(WebhookEvent, ids["new_webhook"])
    await _cleanup_rows(LLMUsage, ids["new_llm"])


async def test_dry_run_counts_and_writes_nothing(owner, s3):
    ids = await _seed(owner)

    counts = await tasks.purge_retention_core(dry_run=True)

    assert counts["runs"] >= 1
    assert counts["raw_objects"] >= 1
    assert counts["audit"] >= 1
    assert counts["webhook_events"] >= 1
    assert counts["llm_usage"] >= 1
    # Nothing changed — rows and objects are all still here.
    assert await _exists(Run, ids["old_run"])
    assert await _exists(Job, ids["old_run"])
    assert await _event_count(ids["old_run"]) == 1
    assert await _exists(Upload, ids["old_upload"])
    assert _object_bytes(f"{owner}/{ids['old_upload']}") == b"data"
    assert await _exists(AuditLog, ids["old_audit"])
    assert await _exists(WebhookEvent, ids["old_webhook"])
    assert await _exists(LLMUsage, ids["old_llm"])

    await _cleanup_audit(ids["old_audit"], ids["new_audit"])
    await _cleanup_rows(
        WebhookEvent, ids["old_webhook"], ids["new_webhook"]
    )
    await _cleanup_rows(LLMUsage, ids["old_llm"], ids["new_llm"])


async def test_the_script_dry_run_prints_json_and_writes_nothing(owner, s3):
    ids = await _seed(owner)

    # Windows' SelectorEventLoop cannot spawn subprocesses; run it in a thread.
    proc = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "scripts/purge_retention.py", "--dry-run"],
        capture_output=True,
        cwd=REPO_ROOT,
    )

    assert proc.returncode == 0, proc.stderr.decode()
    payload = json.loads(proc.stdout.decode())  # stdout is pure JSON — no log noise
    assert payload["dry_run"] is True
    assert payload["runs"] >= 1
    assert await _exists(Run, ids["old_run"])
    assert await _exists(WebhookEvent, ids["old_webhook"])
    assert await _exists(LLMUsage, ids["old_llm"])

    await _cleanup_audit(ids["old_audit"], ids["new_audit"])
    await _cleanup_rows(WebhookEvent, ids["new_webhook"])
    await _cleanup_rows(LLMUsage, ids["new_llm"])
