"""Task 5: keyset pagination on `/api/v1/simulate/debates` (plan §6).

`?limit&cursor` over `(created_at, id)` DESC — stable while new runs arrive —
and the legacy alias keeps today's array shape (R15).
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
from sqlalchemy import delete

import src.api.run_doc as run_doc
from src.api.debate_api import router
from src.api.errors import install_error_handlers
from src.auth.deps import current_user
from src.db.engine import get_session_factory
from src.db.models import User

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set")

pytestmark = [requires_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def accounts(db):
    factory = get_session_factory()
    made = []
    async with factory() as session:
        for _ in range(2):
            user = User(
                email=f"run-truth-{uuid.uuid4().hex[:10]}@example.com",
                password_hash="not-a-real-hash",
            )
            session.add(user)
            await session.commit()
            made.append(SimpleNamespace(id=str(user.id)))
    yield made
    async with factory() as session:
        for account in made:
            await session.execute(delete(User).where(User.id == uuid.UUID(account.id)))
        await session.commit()


@pytest_asyncio.fixture
async def client(accounts):
    owner, _ = accounts
    app = FastAPI()
    install_error_handlers(app)  # the uniform error contract, as on the real app
    app.include_router(router)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=uuid.UUID(owner.id))
    transport = ASGITransport(app=app, client=("10.99.9.1", 5000))
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


async def _seed_runs(user_id: str, count: int) -> list[dict]:
    """`count` runs, one day apart, oldest first — newest is created last."""
    docs = []
    for index in range(count):
        doc = {
            "run_id": str(uuid.uuid4()),
            "user_id": user_id,
            "created_at": f"2026-10-0{index + 1}T10:00:00+00:00",
            "query": f"question {index}",
            "dataset_id": "ds-1",
            "config": {},
            "status": "complete",
            "events": [],
            "result": {"rounds_executed": 1},
        }
        await run_doc.write_run_doc(doc)
        docs.append(doc)
    return docs


async def _walk(client, limit: int) -> list[dict]:
    """Follow next_cursor to the end; fail loudly on a loop."""
    items: list[dict] = []
    cursor = None
    for _ in range(20):  # more than any page count here — a loop means a bug
        query = f"?limit={limit}" + (f"&cursor={cursor}" if cursor else "")
        response = await client.get(f"/api/v1/simulate/debates{query}")
        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == {"items", "next_cursor"}
        items.extend(body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            return items
    raise AssertionError("cursor walk did not terminate")


async def test_walk_with_limit_one_visits_every_run_newest_first(client, accounts):
    owner, _ = accounts
    docs = await _seed_runs(owner.id, 3)

    items = await _walk(client, limit=1)

    assert [item["run_id"] for item in items] == [doc["run_id"] for doc in reversed(docs)]


async def test_last_page_has_a_null_cursor_and_no_extras(client, accounts):
    owner, _ = accounts
    docs = await _seed_runs(owner.id, 3)

    first = (await client.get("/api/v1/simulate/debates?limit=2")).json()
    assert len(first["items"]) == 2
    assert first["next_cursor"] is not None

    second = (
        await client.get(f"/api/v1/simulate/debates?limit=2&cursor={first['next_cursor']}")
    ).json()
    assert [item["run_id"] for item in second["items"]] == [docs[0]["run_id"]]
    assert second["next_cursor"] is None


async def test_a_new_run_mid_walk_does_not_corrupt_paging(client, accounts):
    """Keyset, not offset: a run created during the walk neither duplicates nor
    hides the runs the walk set out to visit."""
    owner, _ = accounts
    docs = await _seed_runs(owner.id, 3)

    first = (await client.get("/api/v1/simulate/debates?limit=2")).json()
    seen = [item["run_id"] for item in first["items"]]

    newer = {**docs[-1], "run_id": str(uuid.uuid4()), "created_at": "2026-11-01T10:00:00+00:00"}
    await run_doc.write_run_doc(newer)

    rest = (
        await client.get(f"/api/v1/simulate/debates?limit=2&cursor={first['next_cursor']}")
    ).json()
    seen.extend(item["run_id"] for item in rest["items"])
    assert rest["next_cursor"] is None

    assert sorted(seen) == sorted(doc["run_id"] for doc in docs)
    assert newer["run_id"] not in seen  # newer than the window, not a duplicate

    fresh = await _walk(client, limit=1)
    assert fresh[0]["run_id"] == newer["run_id"]
    assert sorted(item["run_id"] for item in fresh) == sorted(
        [doc["run_id"] for doc in docs] + [newer["run_id"]]
    )


async def test_other_users_runs_are_not_in_the_page(client, accounts):
    owner, other = accounts
    await _seed_runs(owner.id, 1)
    await _seed_runs(other.id, 1)

    items = await _walk(client, limit=25)

    assert len(items) == 1


async def test_bad_cursor_is_a_400_with_the_uniform_contract(client, accounts):
    response = await client.get("/api/v1/simulate/debates?cursor=not-a-cursor")

    assert response.status_code == 400
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "invalid_cursor"


@pytest.mark.parametrize("limit", [0, 101])
async def test_limit_out_of_bounds_is_422(client, accounts, limit):
    response = await client.get(f"/api/v1/simulate/debates?limit={limit}")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_legacy_alias_keeps_the_array_shape(client, accounts):
    owner, _ = accounts
    docs = await _seed_runs(owner.id, 2)

    legacy = (await client.get("/simulate/debates")).json()
    assert isinstance(legacy, list)
    assert [item["run_id"] for item in legacy] == [doc["run_id"] for doc in reversed(docs)]

    canonical = (await client.get("/api/v1/simulate/debates")).json()
    assert set(canonical) == {"items", "next_cursor"}
    assert [item["run_id"] for item in canonical["items"]] == [doc["run_id"] for doc in reversed(docs)]
