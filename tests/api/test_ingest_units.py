"""Ingest units: reserve the byte ceiling, 402 when exhausted, delete a document."""

import asyncio
import datetime
import math
import os
import sys
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.api.errors import install_error_handlers
from src.api.ingest_api import router as ingest_router
from src.auth.deps import current_user
from src.billing import units
from src.config.settings import get_settings
from src.db.engine import get_session_factory
from src.db.models import Job, Upload, User
from src.ingest import repository, storage
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
    """A real user row — uploads.user_id and jobs.user_id are FKs."""
    factory = get_session_factory()
    async with factory() as session:
        user = User(
            email=f"auth-test-ingest-units-{uuid.uuid4().hex[:10]}@example.com",
            password_hash="not-a-real-hash",
        )
        session.add(user)
        await session.commit()
        user_id = str(user.id)
    yield user_id


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


def _client(user_id: str | None, *, raise_app_exceptions: bool = True) -> AsyncClient:
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(ingest_router, prefix="/api/v1")
    if user_id is not None:
        app.dependency_overrides[current_user] = lambda: SimpleNamespace(
            id=uuid.UUID(str(user_id)), plan_key="free"
        )
    return AsyncClient(
        transport=ASGITransport(
            app=app,
            client=("10.9.9.9", 5000),
            raise_app_exceptions=raise_app_exceptions,
        ),
        base_url="http://testserver",
    )


async def _uploads_for(owner: str) -> list[Upload]:
    factory = get_session_factory()
    async with factory() as session:
        rows = await session.execute(
            select(Upload).where(Upload.user_id == uuid.UUID(owner))
        )
        return list(rows.scalars().all())


async def _jobs_for(owner: str) -> list[Job]:
    factory = get_session_factory()
    async with factory() as session:
        rows = await session.execute(select(Job).where(Job.user_id == uuid.UUID(owner)))
        return list(rows.scalars().all())


async def _job(job_id: str) -> Job | None:
    factory = get_session_factory()
    async with factory() as session:
        return await session.get(Job, uuid.UUID(job_id))


async def _balance(owner: str) -> tuple[int, int]:
    factory = get_session_factory()
    async with factory() as session:
        period_start, _ = await units.resolve_period(session, uuid.UUID(owner))
        return await units.get_balance(session, uuid.UUID(owner), period_start)


async def _exhaust(owner: str) -> datetime.datetime:
    factory = get_session_factory()
    async with factory() as session:
        period_start, period_end = await units.resolve_period(session, uuid.UUID(owner))
        await units.settle_call(
            session,
            user_id=uuid.UUID(owner),
            period_start=period_start,
            source="ingest",
            amount=get_settings().plan_free_units,
            idempotency_key=f"exhaust-{uuid.uuid4().hex}",
        )
    return period_end


async def _seed_row(owner: str, *, object_key: str) -> str:
    factory = get_session_factory()
    upload_id = uuid.uuid4()
    async with factory() as session:
        repository.insert_upload(
            session,
            upload_id=upload_id,
            user_id=uuid.UUID(owner),
            object_key=object_key,
            name="notes.txt",
            size=1,
            mime="text/plain",
            sha256=uuid.uuid4().hex,
        )
        await session.commit()
    return str(upload_id)


# --- the reservation gate -----------------------------------------------------


@pytest.mark.asyncio
async def test_upload_reserves_a_byte_ceiling(owner, s3):
    async with _client(owner) as client:
        response = await client.post(
            "/api/v1/ingest/files",
            files={"files": ("notes.txt", TEXT, "text/plain")},
        )

    assert response.status_code == 202, response.text
    job = await _job(response.json()["job_id"])
    expected = math.ceil(len(TEXT) / get_settings().chars_per_unit)
    assert expected == 1
    assert job.reserved_units == expected
    assert job.reserved_period_start is not None


@pytest.mark.asyncio
async def test_exhausted_units_is_402_and_writes_nothing(owner, s3):
    period_end = await _exhaust(owner)

    async with _client(owner) as client:
        response = await client.post(
            "/api/v1/ingest/files",
            files={"files": ("notes.txt", TEXT, "text/plain")},
        )

    assert response.status_code == 402, response.text
    error = response.json()["error"]
    assert error["code"] == "payment_required"
    assert period_end.date().isoformat() in error["message"]
    assert await _uploads_for(owner) == []
    assert await _jobs_for(owner) == []


@pytest.mark.asyncio
async def test_url_with_exhausted_units_is_402(owner, monkeypatch):
    monkeypatch.setattr("src.api.ingest_api.validate_url", lambda url: url)
    period_end = await _exhaust(owner)

    async with _client(owner) as client:
        response = await client.post(
            "/api/v1/ingest/url", json={"url": "https://example.com/report"}
        )

    assert response.status_code == 402, response.text
    error = response.json()["error"]
    assert error["code"] == "payment_required"
    assert period_end.date().isoformat() in error["message"]


@pytest.mark.asyncio
async def test_enqueue_failure_releases_the_reservation(owner, s3, monkeypatch):
    async def boom(_kind, _payload):
        raise RuntimeError("queue down")

    monkeypatch.setattr("src.api.ingest_api.enqueue_or_http", boom)

    async with _client(owner, raise_app_exceptions=False) as client:
        response = await client.post(
            "/api/v1/ingest/files",
            files={"files": ("notes.txt", TEXT, "text/plain")},
        )

    assert response.status_code == 500, response.text
    assert await _uploads_for(owner) == []
    assert await _jobs_for(owner) == []
    assert storage._client().list_objects_v2(Bucket=BUCKET)["KeyCount"] == 0
    used, reserved = await _balance(owner)
    assert (used, reserved) == (0, 0)


# --- per-document delete ------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_own_upload_removes_row_and_object(owner, monkeypatch):
    key = f"{owner}/doc"
    upload_id = await _seed_row(owner, object_key=key)
    deleted: list[str] = []
    monkeypatch.setattr("src.api.ingest_api.delete_upload", deleted.append)

    async with _client(owner) as client:
        response = await client.delete(f"/api/v1/uploads/{upload_id}")

    assert response.status_code == 204, response.text
    assert deleted == [key]
    assert await _uploads_for(owner) == []


@pytest.mark.asyncio
async def test_foreign_or_unknown_upload_is_404(owner):
    factory = get_session_factory()
    async with factory() as session:
        stranger = User(
            email=f"auth-test-ingest-units-{uuid.uuid4().hex[:10]}@example.com",
            password_hash="not-a-real-hash",
        )
        session.add(stranger)
        await session.commit()
        stranger_id = str(stranger.id)
    foreign_id = await _seed_row(stranger_id, object_key=f"{stranger_id}/doc")

    async with _client(owner) as client:
        foreign = await client.delete(f"/api/v1/uploads/{foreign_id}")
        unknown = await client.delete(f"/api/v1/uploads/{uuid.uuid4()}")

    assert foreign.status_code == 404, foreign.text
    assert unknown.status_code == 404, unknown.text
    assert foreign.json()["error"]["code"] == "not_found"
    assert len(await _uploads_for(stranger_id)) == 1


@pytest.mark.asyncio
async def test_delete_without_a_session_is_401(owner):
    upload_id = await _seed_row(owner, object_key=f"{owner}/doc")

    async with _client(None) as client:
        response = await client.delete(f"/api/v1/uploads/{upload_id}")

    assert response.status_code == 401, response.text


@pytest.mark.asyncio
async def test_deleting_a_url_row_never_calls_s3(owner, monkeypatch):
    upload_id = await _seed_row(owner, object_key="https://example.com/report")
    deleted: list[str] = []
    monkeypatch.setattr("src.api.ingest_api.delete_upload", deleted.append)

    async with _client(owner) as client:
        response = await client.delete(f"/api/v1/uploads/{upload_id}")

    assert response.status_code == 204, response.text
    assert deleted == []
    assert await _uploads_for(owner) == []
