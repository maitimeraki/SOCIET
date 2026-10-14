"""Account lifecycle: delete (soft-disable → purge) and export (zip + URL)."""

import asyncio
import datetime
import io
import json
import os
import sys
import uuid
import zipfile
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from src.api import run_doc
from src.api.account_api import router as account_router
from src.api.errors import install_error_handlers
from src.api.jobs_api import router as jobs_router
from src.auth.deps import current_user
from src.db.engine import get_db, get_session_factory
from src.db.models import Job, Run, Upload, User, UserSession
from src.ingest import repository, storage
from src.jobs import queue as jobs_queue

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)
pytestmark = [requires_db, pytest.mark.asyncio]

BUCKET = "societas-uploads"


@pytest_asyncio.fixture
async def owner(db):
    factory = get_session_factory()
    async with factory() as session:
        user = User(
            email=f"auth-test-account-{uuid.uuid4().hex[:10]}@example.com",
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


@pytest.fixture
def inline_queue(monkeypatch):
    monkeypatch.setenv("QUEUE_MODE", "inline")
    from src.config.settings import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _authed_client(owner_id: str):
    """current_user and get_db share one session holding the real user row, so
    the route's ``user.disabled_at`` write is actually persisted."""
    factory = get_session_factory()
    session = factory()
    user = await session.get(User, uuid.UUID(owner_id))

    app = FastAPI()
    install_error_handlers(app)
    app.include_router(account_router)
    app.include_router(jobs_router, prefix="/api/v1")
    app.dependency_overrides[current_user] = lambda: user

    async def _db():
        yield session

    app.dependency_overrides[get_db] = _db
    client = AsyncClient(
        transport=ASGITransport(app=app, client=("10.3.3.3", 5000)),
        base_url="http://testserver",
    )
    return client, session, user


async def _seed(
    owner_id: str, *, query: str = "Should we expand?", verdict=None
) -> dict:
    owner = uuid.UUID(owner_id)
    run_id = str(uuid.uuid4())
    await run_doc.write_run_doc(
        {
            "run_id": run_id,
            "user_id": owner_id,
            "status": "complete",
            "query": query,
            "dataset_id": "ds",
            "config": {},
            "result": verdict or {"summary": "ok"},
            "error": None,
        }
    )
    upload_id = uuid.uuid4()
    factory = get_session_factory()
    async with factory() as session:
        session.add(
            UserSession(
                user_id=owner,
                expires_at=datetime.datetime.now(datetime.UTC)
                + datetime.timedelta(days=1),
            )
        )
        repository.insert_upload(
            session,
            upload_id=upload_id,
            user_id=owner,
            object_key=f"{owner}/{upload_id}",
            size=4,
            mime="text/plain",
            sha256="sha",
            extracted_text='{"text": "extracted body"}',
        )
        await session.commit()
    storage.put_upload(owner, upload_id, b"data")
    return {"run_id": run_id, "upload_id": upload_id}


async def _count(model, owner_id: str) -> int:
    factory = get_session_factory()
    async with factory() as session:
        return (
            await session.execute(
                select(func.count())
                .select_from(model)
                .where(model.user_id == uuid.UUID(owner_id))
            )
        ).scalar_one()


async def test_delete_soft_disables_then_purges(owner, s3, inline_queue):
    seeded = await _seed(owner)
    client, session, user = await _authed_client(owner)
    try:
        response = await client.request(
            "DELETE", "/api/v1/account", json={"confirm": user.email}
        )
        assert response.status_code == 202, response.text
        job_id = response.json()["job_id"]
        await jobs_queue.drain_inline()
    finally:
        await client.aclose()
        await session.close()

    factory = get_session_factory()
    async with factory() as fresh:
        row = await fresh.get(User, uuid.UUID(owner))
        assert row.disabled_at is not None  # soft delete landed

    assert await _count(UserSession, owner) == 0
    assert await _count(Run, owner) == 0
    assert await _count(Job, owner) == 0
    assert await _count(Upload, owner) == 0
    with pytest.raises(Exception):
        storage.get_upload(f"{owner}/{seeded['upload_id']}")
    assert job_id  # the purge job ran under the id we were handed


async def test_a_wrong_confirmation_is_a_400(owner, s3, inline_queue):
    client, session, user = await _authed_client(owner)
    try:
        response = await client.request(
            "DELETE", "/api/v1/account", json={"confirm": "someone-else@example.com"}
        )
    finally:
        await client.aclose()
        await session.close()

    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "confirmation_mismatch"
    # Nothing was disabled.
    factory = get_session_factory()
    async with factory() as fresh:
        assert (await fresh.get(User, uuid.UUID(owner))).disabled_at is None


async def test_a_second_delete_is_a_conflict(owner, s3, inline_queue):
    client, session, user = await _authed_client(owner)
    try:
        first = await client.request(
            "DELETE", "/api/v1/account", json={"confirm": user.email}
        )
        assert first.status_code == 202
        await jobs_queue.drain_inline()
        second = await client.request(
            "DELETE", "/api/v1/account", json={"confirm": user.email}
        )
    finally:
        await client.aclose()
        await session.close()

    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "account_already_deleted"


async def test_export_zip_contains_the_run_json(owner, s3, inline_queue):
    seeded = await _seed(owner, query="Should we expand into Europe?")
    client, session, user = await _authed_client(owner)
    try:
        response = await client.get("/api/v1/account/export")
        assert response.status_code == 202, response.text
        job_id = response.json()["job_id"]
        await jobs_queue.drain_inline()

        with storage.get_upload(f"exports/{owner}/{job_id}.zip") as body:
            data = body.read()

        status = await client.get(f"/api/v1/jobs/{job_id}")
    finally:
        await client.aclose()
        await session.close()

    with io.BytesIO(data) as buffer, zipfile.ZipFile(buffer) as archive:
        names = archive.namelist()
        assert "runs.json" in names
        assert f"texts/{seeded['upload_id']}.txt" in names
        runs = json.loads(archive.read("runs.json"))
        assert runs and runs[0]["query"] == "Should we expand into Europe?"

    assert status.status_code == 200, status.text
    assert status.json()["download_url"]
