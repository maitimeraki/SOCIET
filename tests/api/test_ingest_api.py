"""Ingest API: the 202 enqueue flow, quota/cap gates, and worker extraction.

The routes never extract — they validate, store to the (mocked) bucket, write
the ``uploads`` rows, and queue one ``extract_upload`` job. Extraction is driven
here by a real ``rq.SimpleWorker`` burst against the local Redis and moto S3.
"""

import asyncio
import os
import sys
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from rq import SimpleWorker
from sqlalchemy import select

from src.api import run_doc
from src.api.errors import install_error_handlers
from src.api.ingest_api import router as ingest_router
from src.auth.deps import current_user
from src.db.engine import get_session_factory
from src.db.models import Upload, User
from src.ingest import storage
from src.jobs import queue as jobs_queue

if sys.platform == "win32":
    # psycopg refuses async on the default ProactorEventLoop (see conftest).
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)
pytestmark = [requires_db]

BUCKET = "societas-uploads"
TEXT = b"Steel tariffs reshape the European market and entry costs."


@pytest_asyncio.fixture
async def owner(db):
    """A real user id — uploads.user_id and jobs.user_id are FKs."""
    factory = get_session_factory()
    async with factory() as session:
        user = User(
            email=f"auth-test-ingest-{uuid.uuid4().hex[:10]}@example.com",
            password_hash="not-a-real-hash",
        )
        session.add(user)
        await session.commit()
        user_id = str(user.id)
    yield user_id
    await _drop_owner(user_id)


@pytest_asyncio.fixture
async def s3(monkeypatch):
    """A mocked S3 with the configured bucket; a fresh client per test."""
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


@pytest.fixture(autouse=True)
def clean_queue():
    queue = jobs_queue.get_queue()
    queue.empty()
    yield
    queue.empty()


def _client(user_id: str | None) -> AsyncClient:
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(ingest_router, prefix="/api/v1")
    if user_id is not None:
        app.dependency_overrides[current_user] = lambda: SimpleNamespace(
            id=uuid.UUID(str(user_id))
        )
    return AsyncClient(
        transport=ASGITransport(app=app, client=("10.9.9.9", 5000)),
        base_url="http://testserver",
    )


def _run(coro):
    """One ``asyncio.run``, disposing the pooled engine after — the worker tests
    must burst outside a loop, and a pooled async connection cannot cross loops."""

    async def _wrapped():
        try:
            return await coro
        finally:
            from src.db.engine import get_engine

            await get_engine().dispose()

    return asyncio.run(_wrapped())


async def _drop_owner(user_id: str) -> None:
    from sqlalchemy import delete

    factory = get_session_factory()
    async with factory() as session:
        await session.execute(delete(User).where(User.id == uuid.UUID(user_id)))
        await session.commit()


async def _make_owner() -> str:
    factory = get_session_factory()
    async with factory() as session:
        user = User(
            email=f"auth-test-ingest-{uuid.uuid4().hex[:10]}@example.com",
            password_hash="not-a-real-hash",
        )
        session.add(user)
        await session.commit()
        return str(user.id)


async def _uploads_for(owner: str) -> list[Upload]:
    factory = get_session_factory()
    async with factory() as session:
        rows = await session.execute(
            select(Upload).where(Upload.user_id == uuid.UUID(owner))
        )
        return list(rows.scalars().all())


def _error(response) -> dict:
    return response.json()["error"]


# --- gates (no storage, no extraction) ---------------------------------------


@pytest.mark.asyncio
async def test_unauthenticated_is_401():
    async with _client(None) as client:
        response = await client.post(
            "/api/v1/ingest/files",
            files={"files": ("a.txt", TEXT, "text/plain")},
        )
    assert response.status_code == 401, response.text


@pytest.mark.asyncio
async def test_too_many_files_is_413(owner):
    files = [("files", (f"f{i}.txt", b"text", "text/plain")) for i in range(21)]
    async with _client(owner) as client:
        response = await client.post("/api/v1/ingest/files", files=files)
    assert response.status_code == 413, response.text
    assert _error(response)["code"] == "payload_too_large"


@pytest.mark.asyncio
async def test_oversize_file_is_413(owner):
    async with _client(owner) as client:
        response = await client.post(
            "/api/v1/ingest/files",
            files={"files": ("big.txt", b"a" * (20 * 1024 * 1024 + 1), "text/plain")},
        )
    assert response.status_code == 413, response.text


@pytest.mark.asyncio
async def test_spoofed_type_is_422(owner):
    # A PDF body under a .txt name: the magic-byte check refuses it before any
    # storage or enqueue (the uniform 422 contract).
    async with _client(owner) as client:
        response = await client.post(
            "/api/v1/ingest/files",
            files={"files": ("fake.txt", b"%PDF-1.7\njunk\n%%EOF\n", "text/plain")},
        )
    assert response.status_code == 422, response.text
    assert _error(response)["code"] == "validation_error"
    assert await _uploads_for(owner) == []


@pytest.mark.asyncio
async def test_url_blank_is_422(owner):
    async with _client(owner) as client:
        response = await client.post("/api/v1/ingest/url", json={"url": "   "})
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_over_quota_is_429_with_retry_after(owner, monkeypatch):
    monkeypatch.setenv("UPLOAD_QUOTA_BYTES_MONTH", "1")
    from src.config.settings import get_settings

    get_settings.cache_clear()
    try:
        async with _client(owner) as client:
            response = await client.post(
                "/api/v1/ingest/files",
                files={"files": ("notes.txt", TEXT, "text/plain")},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 429, response.text
    assert _error(response)["code"] == "quota_exceeded"
    assert int(response.headers["Retry-After"]) >= 1
    assert await _uploads_for(owner) == []


@pytest.mark.asyncio
async def test_url_over_quota_is_429_with_retry_after(owner, monkeypatch):
    # The SSRF guard is out of scope here; the quota gate is what is under test.
    monkeypatch.setattr("src.api.ingest_api.validate_url", lambda url: url)
    monkeypatch.setenv("UPLOAD_QUOTA_FILES_MONTH", "0")
    from src.config.settings import get_settings

    get_settings.cache_clear()
    try:
        async with _client(owner) as client:
            response = await client.post(
                "/api/v1/ingest/url", json={"url": "https://example.com/report"}
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 429, response.text
    assert _error(response)["code"] == "quota_exceeded"
    assert int(response.headers["Retry-After"]) >= 1


# --- the 202 flow + worker extraction ----------------------------------------
#
# These are synchronous: the SimpleWorker burst runs the real task target, which
# calls ``asyncio.run`` — impossible from inside the test's own running loop.


def _post_files(owner: str, filename: str, data: bytes, content_type: str) -> dict:
    async def _go():
        async with _client(owner) as client:
            response = await client.post(
                "/api/v1/ingest/files",
                files={"files": (filename, data, content_type)},
            )
            return response.status_code, response.json()

    return _run(_go())


def _queue_and_burst() -> None:
    SimpleWorker([jobs_queue.get_queue()], connection=jobs_queue.get_redis()).work(
        burst=True
    )


def test_enqueue_stores_and_the_worker_extracts(s3, monkeypatch):
    monkeypatch.setenv("QUEUE_MODE", "rq")
    from src.config.settings import get_settings

    get_settings.cache_clear()
    owner = _run(_make_owner())
    try:
        status, body = _post_files(owner, "notes.txt", TEXT, "text/plain")
        assert status == 202, body
        assert body["status"] == "queued"
        job_id = body["job_id"]

        # Stored + queued, not yet extracted.
        rows = _run(_uploads_for(owner))
        assert len(rows) == 1
        assert rows[0].extracted_text is None
        assert rows[0].sha256
        assert _run(run_doc.read_job_doc(job_id))["status"] == "queued"

        _queue_and_burst()

        done = _run(run_doc.read_job_doc(job_id))
        assert done["status"] == "completed", done
        upload_id = done["result"]["upload_ids"][0]
        row = next(r for r in _run(_uploads_for(owner)) if str(r.id) == upload_id)
        assert "Steel tariffs" in row.extracted_text

        # The payload is served back, owner-checked.
        async def _fetch():
            async with _client(owner) as client:
                return await client.get(
                    f"/api/v1/ingest/documents?upload_ids={upload_id}"
                )

        payload = _run(_fetch()).json()["documents"][0]
        assert payload["title"] == "notes.txt"
        assert "Steel tariffs" in payload["text"]
    finally:
        _run(_drop_owner(owner))
        get_settings.cache_clear()


def test_a_foreign_upload_id_is_not_returned(s3, monkeypatch):
    monkeypatch.setenv("QUEUE_MODE", "rq")
    from src.config.settings import get_settings

    get_settings.cache_clear()
    owner = _run(_make_owner())
    try:
        _post_files(owner, "notes.txt", TEXT, "text/plain")
        _queue_and_burst()
        assert len(_run(_uploads_for(owner))) == 1

        stranger = str(uuid.uuid4())

        async def _fetch():
            async with _client(owner) as client:
                return await client.get(
                    f"/api/v1/ingest/documents?upload_ids={stranger}"
                )

        assert _run(_fetch()).json()["documents"] == []
    finally:
        _run(_drop_owner(owner))
        get_settings.cache_clear()


def test_a_failed_extraction_marks_the_job_failed(s3, monkeypatch):
    monkeypatch.setenv("QUEUE_MODE", "rq")
    from src.config.settings import get_settings

    get_settings.cache_clear()
    owner = _run(_make_owner())
    try:
        # A zip header under .docx passes the magic-byte gate but python-docx
        # cannot read it — the extraction failure must land on the job row.
        status, body = _post_files(
            owner, "broken.docx", b"PK\x03\x04junk", "application/zip"
        )
        assert status == 202, body
        job_id = body["job_id"]

        _queue_and_burst()

        done = _run(run_doc.read_job_doc(job_id))
        assert done["status"] == "failed", done
        assert done["error"]
    finally:
        _run(_drop_owner(owner))
        get_settings.cache_clear()


def test_an_enqueue_refusal_rolls_back_the_staged_upload(s3, monkeypatch):
    # The per-user job cap refuses the enqueue (429) *after* the upload is
    # stored — the row and its object must not survive as an orphan.
    monkeypatch.setenv("MAX_JOBS_PER_USER", "0")
    from src.config.settings import get_settings

    get_settings.cache_clear()
    owner = _run(_make_owner())
    try:
        status, body = _post_files(owner, "notes.txt", TEXT, "text/plain")
        assert status == 429, body
        assert body["error"]["code"] == "job_limit_exceeded"
        assert _run(_uploads_for(owner)) == []
        assert storage._client().list_objects_v2(Bucket=BUCKET)["KeyCount"] == 0
    finally:
        _run(_drop_owner(owner))
        get_settings.cache_clear()
