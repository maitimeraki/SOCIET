"""Agent records: the owner roster and the audited operator read (Task 2.7).

The roster is owner-scoped and returns AgentView only, for published rows, in seat
order. The operator read is role-guarded and audited. Tests that need Postgres are
gated on DATABASE_URL and do not use the purging `db` fixture; the auth, 404 and
audit paths are exercised without a database.
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
from sqlalchemy import delete, func, select

import src.api.run_doc as run_doc
from src import audit
from src.api import operator_api
from src.api.debate_api import router as debate_router
from src.auth.deps import current_user
from src.db.engine import get_db, get_session_factory
from src.db.models import AgentRecordRow, User
from src.persona.agent import Stance
from src.simulation.agent_record import AgentView
from tests.agent_factory import agent_record

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

VIEW_KEYS = {"name", "type", "role", "stance", "strength", "bio", "details", "confidence"}
NOT_FOUND = {"detail": "Not found."}
requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)
pytestmark = pytest.mark.asyncio


def _user(role: str = "user", user_id: uuid.UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(id=user_id or uuid.uuid4(), role=role)


def _app(*routers, user: SimpleNamespace) -> FastAPI:
    app = FastAPI()
    for router in routers:
        app.include_router(router)
    app.dependency_overrides[current_user] = lambda: user

    async def _no_db():
        yield None

    app.dependency_overrides[get_db] = _no_db
    return app


def _client(app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=app, client=("10.7.7.7", 5000))
    return AsyncClient(transport=transport, base_url="http://testserver")


# --- no database: the owner and 404 paths ------------------------------------


async def test_roster_of_an_unknown_run_is_the_flat_404(monkeypatch):
    async def no_run(run_id):
        return None

    monkeypatch.setattr(run_doc, "read_run_head", no_run)
    async with _client(_app(debate_router, user=_user())) as http:
        response = await http.get(f"/simulate/debates/{uuid.uuid4()}/roster")
    assert response.json() == NOT_FOUND


async def test_roster_of_a_foreign_run_is_the_same_404_and_reads_nothing(monkeypatch):
    owner = uuid.uuid4()

    async def foreign_run(run_id):
        return {"run_id": run_id, "user_id": str(owner)}

    async def must_not_read(run_id, owner_id):
        raise AssertionError("roster read for a run the caller does not own")

    monkeypatch.setattr(run_doc, "read_run_head", foreign_run)
    monkeypatch.setattr(run_doc, "read_roster", must_not_read)
    async with _client(_app(debate_router, user=_user())) as http:
        response = await http.get(f"/simulate/debates/{uuid.uuid4()}/roster")
    assert response.status_code == 404
    assert response.json() == NOT_FOUND


async def test_roster_returns_only_the_view_keys(monkeypatch):
    owner = uuid.uuid4()
    view = AgentView(
        name="Lumen Pay",
        type="Competitor",
        role="challenger",
        stance=Stance.NEGATIVE,
        strength=0.7,
        bio="Cuts prices.",
        details="Claim one.",
        confidence=0.6,
    )

    async def owned_run(run_id):
        return {"run_id": run_id, "user_id": str(owner)}

    async def one_view(run_id, owner_id):
        return [view]

    monkeypatch.setattr(run_doc, "read_run_head", owned_run)
    monkeypatch.setattr(run_doc, "read_roster", one_view)
    async with _client(_app(debate_router, user=_user(user_id=owner))) as http:
        body = (await http.get(f"/simulate/debates/{uuid.uuid4()}/roster")).json()
    assert set(body[0]) == VIEW_KEYS


# --- no database: the operator role guard and audit ---------------------------


async def test_operator_read_is_forbidden_to_a_normal_user(monkeypatch):
    async def must_not_read(run_id, node_id):
        raise AssertionError("record read by a user without an operator role")

    monkeypatch.setattr(run_doc, "read_agent_record", must_not_read)
    async with _client(_app(operator_api.router, user=_user("user"))) as http:
        response = await http.get(f"/operator/runs/{uuid.uuid4()}/agents/n1")
    assert response.status_code == 403


@pytest.mark.parametrize("role", ["support", "admin"])
async def test_operator_roles_can_read_and_the_read_is_audited(monkeypatch, role):
    stored = agent_record("n1").model_dump(mode="json")
    audited: list[dict] = []

    async def read(run_id, node_id):
        return stored

    async def record(db, action, **kwargs):
        audited.append({"action": action, **kwargs})

    monkeypatch.setattr(run_doc, "read_agent_record", read)
    monkeypatch.setattr(audit, "record", record)
    run_id = str(uuid.uuid4())
    async with _client(_app(operator_api.router, user=_user(role))) as http:
        response = await http.get(f"/operator/runs/{run_id}/agents/n1")
    assert response.status_code == 200
    assert response.json()["node_id"] == "n1"
    assert audited[0]["action"] == "agent_record_read"
    assert audited[0]["target"] == run_id
    assert audited[0]["meta"] == {"node_id": "n1", "found": True}


async def test_an_unknown_operator_target_is_the_flat_404_and_is_still_audited(monkeypatch):
    audited: list[dict] = []

    async def nothing(run_id, node_id):
        return None

    async def record(db, action, **kwargs):
        audited.append(kwargs)

    monkeypatch.setattr(run_doc, "read_agent_record", nothing)
    monkeypatch.setattr(audit, "record", record)
    async with _client(_app(operator_api.router, user=_user("support"))) as http:
        response = await http.get(f"/operator/runs/{uuid.uuid4()}/agents/nope")
    assert response.json() == NOT_FOUND
    assert audited[0]["meta"]["found"] is False


async def test_a_failed_audit_write_returns_no_record(monkeypatch):
    async def read(run_id, node_id):
        return agent_record("n1").model_dump(mode="json")

    async def audit_down(db, action, **kwargs):
        assert kwargs["required"] is True
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(run_doc, "read_agent_record", read)
    monkeypatch.setattr(audit, "record", audit_down)
    async with _client(_app(operator_api.router, user=_user("admin"))) as http:
        with pytest.raises(RuntimeError, match="audit store unavailable"):
            await http.get(f"/operator/runs/{uuid.uuid4()}/agents/n1")


class _DownSession:
    """A session whose audit insert fails, as when the database is unreachable."""

    def add(self, row):
        raise RuntimeError("db down")

    async def rollback(self):
        return None


async def test_the_real_audit_write_swallows_a_failure_unless_required():
    await audit.record(_DownSession(), "login")


async def test_a_required_audit_write_re_raises_its_failure():
    with pytest.raises(RuntimeError, match="db down"):
        await audit.record(_DownSession(), "agent_record_read", required=True)


async def test_a_failed_record_write_is_logged_and_never_raised(monkeypatch):
    from src.api import debate_api

    async def write_fails(run_id, records):
        raise RuntimeError("db down")

    monkeypatch.setattr(run_doc, "write_agent_records", write_fails)
    await debate_api._persist_agent_records(str(uuid.uuid4()), [agent_record("n1")])


# --- Postgres: the stored roster, seat order and idempotent write -------------


@pytest_asyncio.fixture
async def owner():
    factory = get_session_factory()
    async with factory() as session:
        user = User(
            email=f"roster-test-{uuid.uuid4().hex[:10]}@example.com",
            password_hash="not-a-real-hash",
        )
        session.add(user)
        await session.commit()
        account = SimpleNamespace(id=user.id)
    yield account
    async with factory() as session:
        await session.execute(delete(User).where(User.id == account.id))
        await session.commit()


async def _run_for(owner_id: uuid.UUID) -> str:
    run_id = str(uuid.uuid4())
    await run_doc.write_run_doc(
        {
            "run_id": run_id,
            "user_id": str(owner_id),
            "status": "complete",
            "query": "Should we?",
            "dataset_id": None,
            "config": {},
            "result": {"summary": "ok"},
            "error": None,
        }
    )
    return run_id


@requires_db
async def test_the_stored_roster_is_published_only_in_seat_order(owner):
    run_id = await _run_for(owner.id)
    await run_doc.write_agent_records(
        run_id,
        [
            agent_record("n-third", run_id=run_id, seat=2, name="Third"),
            agent_record("n-rejected", run_id=run_id, status="rejected"),
            agent_record("n-first", run_id=run_id, seat=0, name="First"),
            agent_record("n-second", run_id=run_id, seat=1, name="Second"),
        ],
    )
    roster = await run_doc.read_roster(run_id, owner.id)
    assert [view.name for view in roster] == ["First", "Second", "Third"]


@requires_db
async def test_a_foreign_owner_reads_an_empty_roster(owner):
    run_id = await _run_for(owner.id)
    await run_doc.write_agent_records(run_id, [agent_record("n1", run_id=run_id)])
    assert await run_doc.read_roster(run_id, uuid.uuid4()) == []


@requires_db
async def test_a_repeated_write_neither_duplicates_nor_fails(owner):
    run_id = await _run_for(owner.id)
    records = [agent_record("n1", run_id=run_id), agent_record("n2", run_id=run_id, seat=1)]
    await run_doc.write_agent_records(run_id, records)
    await run_doc.write_agent_records(run_id, records)
    factory = get_session_factory()
    async with factory() as session:
        count = (
            await session.execute(
                select(func.count())
                .select_from(AgentRecordRow)
                .where(AgentRecordRow.run_id == uuid.UUID(run_id))
            )
        ).scalar_one()
    assert count == 2
