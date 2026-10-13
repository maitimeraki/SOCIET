"""Task 4 guards (plan §3, R14/R15): every route authenticates, ownership is
404, and both mounts answer.

These run against the real ``src.api.api_server.app`` — the mount table and the
guards both live there — over the real session-cookie / ws-ticket path (live
Postgres + Redis). No ``dependency_overrides``: these tests ARE the auth
behaviour. The app lifespan (Neo4j bootstrap, LLM probe) never runs; the ASGI
app is driven in-process.
"""

import asyncio
import datetime
import itertools
import json
import os
import sys
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import quote

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import src.api.api_server as api_server
import src.api.debate_api as debate_api
import src.api.run_doc as run_doc
from src.api.api_server import app
from src.api.debate_api import _DEBATE_JOBS
from src.auth import service
from src.config.settings import get_settings
from src.db.engine import get_session_factory
from src.db.models import User, UserSession

if sys.platform == "win32":
    # psycopg refuses to run async on the default ProactorEventLoop (same guard
    # as tests/api/test_auth_api.py).
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set")


def _v1(path: str) -> str:
    """The canonical twin of a legacy path (R15)."""
    if path.startswith("/api/"):
        return path.replace("/api/", "/api/v1/", 1)
    return "/api/v1" + path


def _both_mounts(path: str) -> list[str]:
    return [path, _v1(path)]


def _error(response) -> dict:
    body = response.json()
    assert set(body) == {"error"}, body
    return body["error"]


def _cookie(account) -> dict:
    return {"sid": account.sid}


_IPS = itertools.count(11)


@pytest_asyncio.fixture
async def client():
    """ASGI client with a per-test remote address: the rate-limit bucket is
    keyed by client IP, so an isolated IP means an isolated bucket."""
    transport = ASGITransport(app=app, client=(f"10.99.1.{next(_IPS)}", 5000))
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


@pytest_asyncio.fixture
async def accounts(db):
    """Two accounts with one live session each — (owner, other).

    Created as rows (no signup round-trip): the guard tests never verify a
    password, they only need a resolvable sid. The ``db`` fixture purges
    ``auth-test-%`` accounts before and after the test.
    """
    now = datetime.datetime.now(datetime.UTC)
    factory = get_session_factory()
    made = []
    async with factory() as session:
        for _ in range(2):
            user = User(
                email=f"auth-test-{uuid.uuid4().hex[:10]}@example.com",
                password_hash="not-a-real-hash",
            )
            session.add(user)
            await session.flush()  # server-generated id
            user_session = UserSession(
                user_id=user.id, expires_at=now + datetime.timedelta(days=1)
            )
            session.add(user_session)
            await session.flush()
            made.append(SimpleNamespace(id=str(user.id), sid=str(user_session.id)))
        await session.commit()
    return made[0], made[1]


@pytest.fixture(autouse=True)
def _isolate_job_state():
    """Remove only the jobs this test registered; leave module state as found."""
    before_debates, before_runs = set(_DEBATE_JOBS), set(api_server.RUNS)
    yield
    for job_id in set(_DEBATE_JOBS) - before_debates:
        _DEBATE_JOBS.pop(job_id, None)
    for job_id in set(api_server.RUNS) - before_runs:
        api_server.RUNS.pop(job_id, None)


def _owned_job(account, **extra) -> dict:
    job = {
        "job_id": extra.pop("job_id", f"guard-{uuid.uuid4()}"),
        "user_id": account.id,
        "status": "queued",
        "query": "Should we tax carbon?",
        "graph_id": "ds-1",
        "config": {},
        "result": None,
        "error": None,
    }
    job.update(extra)
    return job


# --- the R15 mount table (no DB needed) --------------------------------------


def test_both_mounts_serve_every_route():
    """The controller-verified path list, both mounts, HTTP and WS."""
    http_paths, ws_paths = set(), set()
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if methods:
            http_paths.add(route.path)
        elif "simulate" in getattr(route, "path", ""):
            ws_paths.add(route.path)

    for path in (
        "/simulate/debate",
        "/simulate/debates",
        "/simulate/debates/{run_id}",
        "/simulate/jobs/{job_id}",
        "/simulate/ontology",
        "/simulate/build_graph",
        "/simulate/normalize_graph",
        "/simulate/{job_id}",
        "/api/personas/hatch",
        "/api/ingest/files",
        "/api/ingest/url",
    ):
        assert path in http_paths, path
        assert _v1(path) in http_paths, _v1(path)

    for path in ("/simulate/{job_id}/stream", "/simulate/{job_id}/graph_stream"):
        assert path in ws_paths, path
        assert _v1(path) in ws_paths, _v1(path)


@pytest.mark.asyncio
async def test_probes_stay_public(client):
    assert (await client.get("/health")).status_code == 200


@pytest.mark.asyncio
async def test_retired_simulate_stubs_are_untouched(client):
    """R20: /simulate and /simulate/async keep their 501 — no guard, no v1 twin."""
    one = await client.post("/simulate", json={"scenario": "Should we expand?"})
    two = await client.post("/simulate/async", json={"scenario": "Should we expand?"})
    assert one.status_code == 501
    assert two.status_code == 501


# --- unauthenticated -> 401 uniform, both mounts -----------------------------

_GUARDED = [
    ("POST", "/simulate/debate", {"json": {"query": "Should we tax carbon?"}}),
    ("GET", "/simulate/debates", {}),
    ("GET", "/simulate/debates/some-run", {}),
    ("GET", "/simulate/jobs/some-job", {}),
    ("GET", "/simulate/some-job", {}),
    ("POST", "/simulate/ontology", {"params": {"dataset_id": "ds"}, "json": []}),
    ("POST", "/simulate/build_graph", {"params": {"dataset_id": "ds"}, "json": []}),
    ("POST", "/simulate/normalize_graph", {"params": {"dataset_id": "ds"}}),
    ("POST", "/api/personas/hatch", {"json": {"query": "Who should decide?"}}),
    ("POST", "/api/ingest/url", {"json": {"url": "https://example.com/a.txt"}}),
    ("POST", "/api/ingest/files", {"files": {"files": ("a.txt", b"hello", "text/plain")}}),
]


@requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,kwargs",
    [pytest.param(m, p, kw, id=f"{m} {p}") for m, p, kw in _GUARDED]
    + [pytest.param(m, _v1(p), kw, id=f"{m} {_v1(p)}") for m, p, kw in _GUARDED],
)
async def test_unauthenticated_requests_get_the_uniform_401(client, method, path, kwargs):
    response = await client.request(method, path, **kwargs)
    assert response.status_code == 401, response.text
    assert _error(response)["code"] == "unauthorized"


# --- ownership: owner normal, non-owner 404 ----------------------------------


@requires_db
@pytest.mark.asyncio
async def test_debate_status_is_owner_only(client, accounts):
    owner, other = accounts
    job = _owned_job(owner)
    _DEBATE_JOBS[job["job_id"]] = job

    mine = await client.get(f"/simulate/{job['job_id']}", cookies=_cookie(owner))
    theirs = await client.get(f"/simulate/{job['job_id']}", cookies=_cookie(other))

    assert mine.status_code == 200
    assert mine.json()["job_id"] == job["job_id"]
    assert theirs.status_code == 404
    assert _error(theirs)["code"] == "not_found"


@requires_db
@pytest.mark.asyncio
async def test_a_legacy_job_without_an_owner_is_not_found(client, accounts):
    """R14: a doc predating guards is unownable — not found even for the caller."""
    owner, _ = accounts
    job = _owned_job(owner, job_id=f"legacy-{uuid.uuid4()}")
    job.pop("user_id")
    _DEBATE_JOBS[job["job_id"]] = job

    response = await client.get(f"/simulate/{job['job_id']}", cookies=_cookie(owner))
    assert response.status_code == 404


@requires_db
@pytest.mark.asyncio
async def test_simulate_job_status_is_owner_only(client, accounts):
    owner, other = accounts
    job = _owned_job(owner)
    api_server.RUNS[job["job_id"]] = job

    mine = await client.get(f"/simulate/jobs/{job['job_id']}", cookies=_cookie(owner))
    theirs = await client.get(f"/simulate/jobs/{job['job_id']}", cookies=_cookie(other))

    assert mine.status_code == 200
    assert theirs.status_code == 404
    assert _error(theirs)["code"] == "not_found"


@requires_db
@pytest.mark.asyncio
async def test_run_docs_are_listed_and_read_for_their_owner_only(
    client, accounts, monkeypatch, tmp_path
):
    owner, other = accounts
    monkeypatch.setattr(run_doc, "RUNS_DIR", tmp_path)
    for run_id, user_id in (
        ("run-mine", owner.id),
        ("run-theirs", other.id),
        ("run-legacy", None),
    ):
        run_doc.write_run_doc(
            {
                "run_id": run_id,
                "user_id": user_id,
                "created_at": "2026-10-02T10:00:00+00:00",
                "query": f"question {run_id}",
                "events": [],
            }
        )

    listing = await client.get("/simulate/debates", cookies=_cookie(owner))
    assert listing.status_code == 200
    assert [doc["run_id"] for doc in listing.json()] == ["run-mine"]

    mine = await client.get("/simulate/debates/run-mine", cookies=_cookie(owner))
    theirs = await client.get("/simulate/debates/run-theirs", cookies=_cookie(owner))
    legacy = await client.get("/simulate/debates/run-legacy", cookies=_cookie(owner))

    assert mine.status_code == 200
    assert theirs.status_code == 404
    assert legacy.status_code == 404


# --- both mounts, authenticated ----------------------------------------------


@requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize("path", _both_mounts("/api/personas/hatch"))
async def test_hatch_is_guarded_on_both_mounts(client, accounts, path):
    owner, _ = accounts
    response = await client.post(path, json={"query": "   "}, cookies=_cookie(owner))
    # 400 (blank query) proves auth passed and the handler ran — no Neo4j call.
    assert response.status_code == 400


@requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize("path", _both_mounts("/api/ingest/url"))
async def test_ingest_url_is_guarded_on_both_mounts(client, accounts, path):
    owner, _ = accounts
    response = await client.post(path, json={"url": "   "}, cookies=_cookie(owner))
    assert response.status_code == 422


@requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize("path", _both_mounts("/api/ingest/files"))
async def test_ingest_files_is_guarded_on_both_mounts(client, accounts, path):
    owner, _ = accounts
    response = await client.post(
        path,
        files={"files": ("notes.txt", b"hello world", "text/plain")},
        cookies=_cookie(owner),
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["documents"]) == 1


@requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize("path", _both_mounts("/simulate/debate"))
async def test_debate_enqueue_records_the_owner_on_both_mounts(
    client, accounts, monkeypatch, path
):
    owner, _ = accounts
    monkeypatch.setattr(debate_api, "_run_debate_async", AsyncMock(return_value=None))

    response = await client.post(
        path, json={"query": "Should we tax carbon?"}, cookies=_cookie(owner)
    )

    assert response.status_code == 202, response.text
    job = _DEBATE_JOBS[response.json()["job_id"]]
    assert job["user_id"] == owner.id  # R14: ownership recorded at creation


# --- WebSocket handshake -----------------------------------------------------


class _WS:
    """The ASGI websocket protocol driven in-process: every frame the route
    sends is captured, so "refused before accept" is directly assertable."""

    def __init__(self, task, frames, inbox):
        self.task = task
        self.frames = frames
        self.inbox = inbox

    @property
    def accepted(self) -> bool:
        return any(frame["type"] == "websocket.accept" for frame in self.frames)

    async def _until(self, predicate, timeout: float = 5.0):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            frame = predicate()
            if frame is not None:
                return frame
            if self.task.done():
                self.task.result()  # a crashed route fails the test with its error
                break
            await asyncio.sleep(0.01)
        detail = "timed out" if not self.task.done() else "route returned"
        raise AssertionError(f"no matching frame ({detail}); got {self.frames}")

    async def first(self):
        return await self._until(lambda: self.frames[0] if self.frames else None)

    async def wait_for(self, kind: str):
        return await self._until(
            lambda: next((f for f in self.frames if f["type"] == kind), None)
        )

    async def send_text(self, text: str) -> None:
        await self.inbox.put({"type": "websocket.receive", "text": text})

    async def aclose(self) -> None:
        await self.inbox.put({"type": "websocket.disconnect", "code": 1000})
        try:
            await asyncio.wait_for(self.task, 5.0)
        except asyncio.TimeoutError:  # pragma: no cover - a route that will not stop
            self.task.cancel()


async def _open_ws(path: str, *, ticket: str | None = None, sid: str | None = None) -> _WS:
    headers = [(b"host", b"testserver")]
    if sid is not None:
        headers.append((b"cookie", f"sid={sid}".encode()))
    scope = {
        "type": "websocket",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "scheme": "ws",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 50000),
        "root_path": "",
        "path": path,
        "raw_path": path.encode(),
        "query_string": (f"ticket={quote(ticket)}" if ticket else "").encode(),
        "headers": headers,
        "subprotocols": [],
    }
    frames: list[dict] = []
    inbox: asyncio.Queue = asyncio.Queue()

    async def receive():
        return await inbox.get()

    async def send(message):
        frames.append(message)

    task = asyncio.create_task(app(scope, receive, send))
    # The ASGI server's first frame: `accept()` awaits it (starlette consumes
    # the connect message itself before replying ACCEPT).
    await inbox.put({"type": "websocket.connect"})
    return _WS(task, frames, inbox)


def _stream_job(account, job_id: str) -> str:
    _DEBATE_JOBS[job_id] = _owned_job(account, job_id=job_id)
    return job_id


@requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize("path", _both_mounts("/simulate/{job}/stream"))
async def test_debate_stream_refuses_an_unauthenticated_handshake(accounts, path):
    owner, _ = accounts
    ws = await _open_ws(path.format(job=_stream_job(owner, f"ws-{uuid.uuid4()}")))

    frame = await ws.first()
    assert frame["type"] == "websocket.close"
    assert frame["code"] == 4401
    assert not ws.accepted
    await ws.aclose()


@requires_db
@pytest.mark.asyncio
async def test_debate_stream_refuses_a_non_owners_ticket(accounts, redis_reset):
    owner, other = accounts
    job_id = _stream_job(owner, f"ws-{uuid.uuid4()}")
    ticket = await service.issue_ws_ticket(uuid.UUID(other.id))

    ws = await _open_ws(f"/simulate/{job_id}/stream", ticket=ticket)

    frame = await ws.first()
    assert frame["type"] == "websocket.close"
    assert frame["code"] == 4404
    assert not ws.accepted
    await ws.aclose()


@requires_db
@pytest.mark.asyncio
async def test_debate_stream_accepts_a_ticket_once_and_rejects_the_reuse(accounts, redis_reset):
    owner, _ = accounts
    job_id = _stream_job(owner, f"ws-{uuid.uuid4()}")
    ticket = await service.issue_ws_ticket(uuid.UUID(owner.id))

    first = await _open_ws(f"/simulate/{job_id}/stream", ticket=ticket)
    frame = await first.first()
    assert frame["type"] == "websocket.accept"

    # The accepted socket streams: an inbound frame comes back as an ack.
    await first.send_text("hello")
    ack = await first.wait_for("websocket.send")
    assert json.loads(ack["text"]) == {"type": "ack", "data": "hello"}
    await first.aclose()

    reused = await _open_ws(f"/simulate/{job_id}/stream", ticket=ticket)
    refusal = await reused.first()
    assert refusal["type"] == "websocket.close"
    assert refusal["code"] == 4401
    assert not reused.accepted
    await reused.aclose()


@requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize("path", _both_mounts("/simulate/{job}/stream"))
async def test_debate_stream_accepts_the_session_cookie(accounts, path):
    owner, _ = accounts
    job_id = _stream_job(owner, f"ws-{uuid.uuid4()}")

    ws = await _open_ws(path.format(job=job_id), sid=owner.sid)

    frame = await ws.first()
    assert frame["type"] == "websocket.accept"
    await ws.aclose()


@requires_db
@pytest.mark.asyncio
async def test_graph_stream_refuses_an_unauthenticated_handshake():
    ws = await _open_ws(f"/simulate/{uuid.uuid4()}/graph_stream")

    frame = await ws.first()
    assert frame["type"] == "websocket.close"
    assert frame["code"] == 4401
    assert not ws.accepted
    await ws.aclose()


@requires_db
@pytest.mark.asyncio
async def test_graph_stream_refuses_a_non_owners_ticket(accounts, redis_reset):
    owner, other = accounts
    job_id = f"ws-{uuid.uuid4()}"
    api_server.RUNS[job_id] = {"user_id": owner.id, "status": "running", "result": {"dataset_id": "ds-1"}}
    ticket = await service.issue_ws_ticket(uuid.UUID(other.id))

    ws = await _open_ws(f"/simulate/{job_id}/graph_stream", ticket=ticket)

    frame = await ws.first()
    assert frame["type"] == "websocket.close"
    assert frame["code"] == 4404
    assert not ws.accepted
    await ws.aclose()


@requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize("path", _both_mounts("/simulate/{job}/graph_stream"))
async def test_graph_stream_accepts_the_session_cookie(accounts, path):
    owner, _ = accounts
    job_id = f"ws-{uuid.uuid4()}"
    # Owned, terminal, dataset-less: after accept the route says done and leaves.
    api_server.RUNS[job_id] = {"user_id": owner.id, "status": "failed", "result": {}}

    ws = await _open_ws(path.format(job=job_id), sid=owner.sid)

    assert (await ws.first())["type"] == "websocket.accept"
    done = await ws.wait_for("websocket.send")
    assert json.loads(done["text"]) == {"type": "done"}
    await ws.aclose()


# --- enqueue gates -----------------------------------------------------------


@requires_db
@pytest.mark.asyncio
async def test_debate_enqueue_is_rate_limited(client, accounts, monkeypatch):
    owner, _ = accounts
    monkeypatch.setattr(debate_api, "_run_debate_async", AsyncMock(return_value=None))
    monkeypatch.setenv("RATE_LIMIT_DEBATE_ENQUEUE", "1/minute")
    get_settings.cache_clear()
    try:
        first = await client.post(
            "/simulate/debate", json={"query": "Should we tax carbon?"}, cookies=_cookie(owner)
        )
        second = await client.post(
            "/simulate/debate", json={"query": "Should we tax carbon?"}, cookies=_cookie(owner)
        )
    finally:
        get_settings.cache_clear()

    assert first.status_code == 202, first.text
    assert second.status_code == 429, second.text
    assert _error(second)["code"] == "rate_limited"


@requires_db
@pytest.mark.asyncio
async def test_debate_enqueue_is_refused_while_degraded(client, accounts, monkeypatch):
    owner, _ = accounts
    # Set at boot by the lifespan probe; absent when the app is driven directly.
    monkeypatch.setattr(app.state, "degraded", True, raising=False)

    response = await client.post(
        "/simulate/debate", json={"query": "Should we tax carbon?"}, cookies=_cookie(owner)
    )

    assert response.status_code == 503
    assert _error(response)["code"] == "service_unavailable"


@requires_db
@pytest.mark.asyncio
async def test_ready_stays_public(client, monkeypatch):
    """/ready is a probe: reachable without a session (verdict cached, no LLM call)."""
    monkeypatch.setattr(api_server, "_llm_healthy", AsyncMock(return_value=True))

    response = await client.get("/ready")

    assert response.status_code != 401, response.text
