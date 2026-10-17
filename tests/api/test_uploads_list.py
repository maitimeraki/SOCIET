"""The documents section's data: the user's uploads, honest about what was read."""

import asyncio
import os
import sys
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from src.auth.deps import current_user
from src.db.engine import get_session_factory
from src.db.models import Upload, User

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)
pytestmark = [requires_db, pytest.mark.asyncio]

# Step 1 resolves this import to the real router module; the rest of the file
# uses `uploads_router` as the single name to mount.
from src.api.ingest_api import router as uploads_router  # noqa: E402


@pytest_asyncio.fixture
async def account():
    factory = get_session_factory()
    async with factory() as session:
        user = User(email=f"uploads-{uuid.uuid4().hex[:10]}@example.com", password_hash="x")
        session.add(user)
        await session.commit()
        made = SimpleNamespace(id=str(user.id))
    yield made
    async with factory() as session:
        await session.execute(delete(User).where(User.id == uuid.UUID(made.id)))
        await session.commit()


@pytest_asyncio.fixture
async def client(account):
    app = FastAPI()
    for prefix in ("", "/api/v1"):
        app.include_router(uploads_router, prefix=prefix)
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=uuid.UUID(account.id))
    transport = ASGITransport(app=app, client=("10.99.8.1", 5000))
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


async def _add_upload(user_id: str, object_key: str, *, read: bool, mime: str = "application/pdf") -> Upload:
    factory = get_session_factory()
    async with factory() as session:
        row = Upload(
            id=uuid.uuid4(),
            user_id=uuid.UUID(user_id), object_key=object_key, bytes=1024, mime=mime,
            sha256=uuid.uuid4().hex,
            extracted_text="text" if read else None,
        )
        session.add(row)
        await session.commit()
        return row


async def test_lists_the_users_uploads_newest_first(account, client):
    await _add_upload(account.id, f"{account.id}/old.pdf", read=True)
    await _add_upload(account.id, f"{account.id}/new.pdf", read=False)
    response = await client.get("/api/v1/uploads")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
    assert items[0]["name"] == "new.pdf"
    assert items[1]["name"] == "old.pdf"


async def test_item_shape_is_honest(account, client):
    row = await _add_upload(account.id, f"{account.id}/report.pdf", read=True)
    item = (await client.get("/api/v1/uploads")).json()["items"][0]
    assert item["id"] == str(row.id)
    assert item["name"] == "report.pdf"
    assert item["bytes"] == 1024
    assert item["mime"] == "application/pdf"
    assert item["read"] is True
    assert item["dataset_id"] is None
    assert item["dataset_name"] is None
    assert item["created_at"]


async def test_unread_upload_is_not_read(account, client):
    await _add_upload(account.id, f"{account.id}/still-reading.pdf", read=False)
    item = (await client.get("/api/v1/uploads")).json()["items"][0]
    assert item["read"] is False


async def test_scoped_to_the_owner(account, client):
    """Another user's uploads are invisible — scope, not a filter the caller can drop."""
    factory = get_session_factory()
    async with factory() as session:
        other = User(email=f"uploads-other-{uuid.uuid4().hex[:10]}@example.com", password_hash="x")
        session.add(other)
        await session.commit()
        other_id = str(other.id)
    await _add_upload(other_id, f"{other_id}/theirs.pdf", read=True)
    items = (await client.get("/api/v1/uploads")).json()["items"]
    assert items == []
    async with factory() as session:
        await session.execute(delete(User).where(User.id == uuid.UUID(other_id)))
        await session.commit()


async def test_limit_bounds(account, client):
    for index in range(3):
        await _add_upload(account.id, f"{account.id}/f{index}.pdf", read=True)
    items = (await client.get("/api/v1/uploads", params={"limit": 2})).json()["items"]
    assert len(items) == 2
