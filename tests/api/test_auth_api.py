"""HTTP-level auth flow tests.

The requests run against a minimal app that mounts only the auth router: the
real api_server app's lifespan probes Neo4j and a live LLM, which is out of
scope here. A separate (always-on) test asserts the router is mounted on the
real app.
"""

import asyncio
import datetime
import os
import sys
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.auth_api import router as auth_router
from src.api.auth_api import ws_ticket_router
from src.api.errors import install_error_handlers
from src.auth import service
from src.auth.cookies import CSRF_COOKIE, CSRF_HEADER
from src.config.settings import get_settings
from src.db.models import UserSession

if sys.platform == "win32":
    # psycopg refuses to run async on the default ProactorEventLoop (same
    # guard as tests/db/conftest.py).
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)

PASSWORD = "hunter2hunter2"

_app = FastAPI()
install_error_handlers(_app)  # the uniform error contract, as on the real app
_app.include_router(auth_router)
_app.include_router(ws_ticket_router)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=_app), base_url="http://testserver")


def _email() -> str:
    return f"auth-test-{uuid.uuid4().hex[:10]}@example.com"


def _csrf(client: AsyncClient) -> dict:
    return {CSRF_HEADER: client.cookies.get(CSRF_COOKIE)}


async def _signup(client: AsyncClient, email: str | None = None) -> str:
    email = email or _email()
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": PASSWORD,
            "accept_terms": True,
            "age_confirmed": True,
        },
    )
    assert response.status_code == 201, response.text
    return email


async def _login(client: AsyncClient, email: str, password: str = PASSWORD):
    return await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )


# --- routing -----------------------------------------------------------------


def test_auth_router_is_mounted_on_the_app():
    from src.api.api_server import app

    paths = {route.path for route in app.routes}
    assert {
        "/api/v1/auth/signup",
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
        "/api/v1/auth/password",
        "/api/v1/auth/sessions",
        "/api/v1/auth/sessions/{session_id}",
        "/api/v1/ws-ticket",
        "/api/v1/billing/usage",
    } <= paths


def test_router_exposes_exactly_the_specified_paths():
    paths = {route.path for route in auth_router.routes}
    assert paths == {
        "/api/v1/auth/signup",
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
        "/api/v1/auth/password",
        "/api/v1/auth/sessions",
        "/api/v1/auth/sessions/{session_id}",
        "/api/v1/auth/verify",
        "/api/v1/auth/verify/send",
        "/api/v1/auth/reset/request",
        "/api/v1/auth/reset/confirm",
    }
    methods = {route.path: route.methods for route in auth_router.routes}
    assert "POST" in methods["/api/v1/auth/signup"]
    assert "DELETE" in methods["/api/v1/auth/sessions/{session_id}"]

    ws_paths = {route.path for route in ws_ticket_router.routes}
    assert ws_paths == {"/api/v1/ws-ticket"}
    assert "POST" in next(iter(ws_ticket_router.routes)).methods


# --- account lifecycle -------------------------------------------------------


@requires_db
@pytest.mark.asyncio
async def test_signup_sets_session_and_csrf_cookies(db):
    async with _client() as client:
        response = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": _email(),
                "password": PASSWORD,
                "accept_terms": True,
                "age_confirmed": True,
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "email", "role", "plan", "created_at"}
    assert body["role"] == "user"
    assert body["plan"] == "free"
    assert "argon2" not in response.text and PASSWORD not in response.text

    set_cookies = response.headers.get_list("set-cookie")
    session_cookie = next(h for h in set_cookies if h.startswith("sid="))
    csrf_cookie = next(h for h in set_cookies if h.startswith("csrf="))
    assert "HttpOnly" in session_cookie
    assert "SameSite=lax" in session_cookie
    assert "HttpOnly" not in csrf_cookie


@pytest.mark.asyncio
async def test_signup_validation_errors_are_422():
    # Pre-existing: needs DATABASE_URL. `get_db` resolves before the body is
    # validated, so with no session factory the request 500s before the 422.
    async with _client() as client:
        short_password = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": _email(),
                "password": "short",
                "accept_terms": True,
                "age_confirmed": True,
            },
        )
        bad_email = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": "not-an-email",
                "password": PASSWORD,
                "accept_terms": True,
                "age_confirmed": True,
            },
        )

    assert short_password.status_code == 422
    assert bad_email.status_code == 422


@requires_db
@pytest.mark.asyncio
async def test_duplicate_signup_returns_409(db):
    email = _email()
    async with _client() as client:
        first = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": email,
                "password": PASSWORD,
                "accept_terms": True,
                "age_confirmed": True,
            },
        )
    async with _client() as duplicate_client:
        second = await duplicate_client.post(
            "/api/v1/auth/signup",
            json={
                "email": email.upper(),
                "password": PASSWORD,
                "accept_terms": True,
                "age_confirmed": True,
            },
        )

    assert first.status_code == 201
    assert second.status_code == 409


@requires_db
@pytest.mark.asyncio
async def test_login_returns_the_user_and_cookies(db):
    email = _email()
    async with _client() as signup_client:
        await _signup(signup_client, email)

    async with _client() as client:
        response = await _login(client, email)
        me = await client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == email
    assert "argon2" not in response.text
    assert me.status_code == 200
    assert me.json()["email"] == email


@requires_db
@pytest.mark.asyncio
async def test_me_carries_role_plan_and_entitlements(db):
    async with _client() as client:
        await _signup(client, _email())
        response = await client.get("/api/v1/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "user"
    assert body["plan"] == "free"
    assert set(body["entitlements"]) == {
        "max_agents",
        "max_rounds",
        "units_remaining",
        "period_end",
    }
    assert body["entitlements"]["max_agents"] == 10
    assert body["entitlements"]["max_rounds"] == 3
    assert body["entitlements"]["units_remaining"] == 1000
    assert body["entitlements"]["period_end"]


@requires_db
@pytest.mark.asyncio
async def test_wrong_password_and_unknown_email_are_indistinguishable(db):
    email = _email()
    async with _client() as signup_client:
        await _signup(signup_client, email)

    async with _client() as client:
        wrong_password = await _login(client, email, "totally-wrong")
        unknown_email = await _login(client, _email(), "totally-wrong")

    assert wrong_password.status_code == unknown_email.status_code == 401
    for response in (wrong_password, unknown_email):
        # The uniform error contract (plan §6); the bodies stay indistinguishable.
        error = response.json()["error"]
        assert error["code"] == "unauthorized"
        assert error["message"] == "Email or password is incorrect."


@requires_db
@pytest.mark.asyncio
async def test_logout_clears_cookies_and_deletes_the_row(db):
    async with _client() as client:
        await _signup(client, _email())
        sid = uuid.UUID(client.cookies.get("sid"))

        response = await client.post("/api/v1/auth/logout", headers=_csrf(client))
        after = await client.get("/api/v1/auth/me")

    assert response.status_code == 204
    assert not client.cookies.get("sid")
    assert not client.cookies.get("csrf")
    assert after.status_code == 401
    assert await db.get(UserSession, sid) is None


# --- session validity --------------------------------------------------------


@requires_db
@pytest.mark.asyncio
async def test_me_without_a_cookie_is_401(db):
    async with _client() as client:
        response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@requires_db
@pytest.mark.asyncio
async def test_authenticated_requests_bump_last_seen_at(db):
    async with _client() as client:
        await _signup(client, _email())
        row = await db.get(UserSession, uuid.UUID(client.cookies.get("sid")))
        stale = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
        row.last_seen_at = stale
        await db.commit()

        assert (await client.get("/api/v1/auth/me")).status_code == 200

        await db.refresh(row)
        assert row.last_seen_at > stale


@requires_db
@pytest.mark.asyncio
async def test_me_rejects_expired_and_revoked_sessions(db):
    async with _client() as client:
        await _signup(client, _email())
        row = await db.get(UserSession, uuid.UUID(client.cookies.get("sid")))
        row.expires_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
            seconds=1
        )
        await db.commit()
        expired = await client.get("/api/v1/auth/me")

    async with _client() as client:
        await _signup(client, _email())
        row = await db.get(UserSession, uuid.UUID(client.cookies.get("sid")))
        row.revoked_at = datetime.datetime.now(datetime.UTC)
        await db.commit()
        revoked = await client.get("/api/v1/auth/me")

    assert expired.status_code == revoked.status_code == 401


@requires_db
@pytest.mark.asyncio
async def test_password_change_revokes_other_sessions_but_not_the_caller(db):
    email = _email()
    async with _client() as caller, _client() as other:
        await _signup(caller, email)
        assert (await _login(other, email)).status_code == 200

        response = await caller.post(
            "/api/v1/auth/password",
            json={"current_password": PASSWORD, "new_password": "brand-new-password"},
            headers=_csrf(caller),
        )

        assert response.status_code == 204
        assert (await caller.get("/api/v1/auth/me")).status_code == 200
        assert (await other.get("/api/v1/auth/me")).status_code == 401

    async with _client() as fresh:
        assert (await _login(fresh, email, "brand-new-password")).status_code == 200
    async with _client() as stale:
        assert (await _login(stale, email, PASSWORD)).status_code == 401


@requires_db
@pytest.mark.asyncio
async def test_sessions_list_and_revoke(db):
    email = _email()
    async with _client() as mine, _client() as other_device:
        await _signup(mine, email)
        assert (await _login(other_device, email)).status_code == 200

        listed = await mine.get("/api/v1/auth/sessions")
        assert listed.status_code == 200
        rows = listed.json()
        assert {r["id"] for r in rows} == {
            mine.cookies.get("sid"),
            other_device.cookies.get("sid"),
        }
        assert all(
            set(r) == {"id", "created_at", "last_seen_at", "user_agent", "ip"}
            for r in rows
        )
        assert all(r["ip"] == "127.0.0.1" for r in rows)

        target = other_device.cookies.get("sid")
        revoked = await mine.delete(
            f"/api/v1/auth/sessions/{target}", headers=_csrf(mine)
        )
        assert revoked.status_code == 204
        assert (await other_device.get("/api/v1/auth/me")).status_code == 401

        remaining = await mine.get("/api/v1/auth/sessions")
        assert [r["id"] for r in remaining.json()] == [mine.cookies.get("sid")]


@requires_db
@pytest.mark.asyncio
async def test_cannot_revoke_another_users_session(db):
    async with _client() as mine, _client() as stranger:
        await _signup(mine, _email())
        await _signup(stranger, _email())

        response = await stranger.delete(
            f"/api/v1/auth/sessions/{mine.cookies.get('sid')}", headers=_csrf(stranger)
        )

    assert response.status_code == 404


# --- CSRF over HTTP ----------------------------------------------------------


@requires_db
@pytest.mark.asyncio
async def test_csrf_required_on_state_changing_requests(db):
    async with _client() as client:
        await _signup(client, _email())

        missing = await client.post("/api/v1/auth/logout")
        mismatched = await client.post(
            "/api/v1/auth/logout", headers={CSRF_HEADER: "not-the-cookie"}
        )
        # Raw latin-1 byte 0xE9: the header reaches the app as a non-ASCII str.
        non_ascii = await client.post(
            "/api/v1/auth/logout", headers={b"X-CSRF-Token": b"\xe9"}
        )
        accepted = await client.post("/api/v1/auth/logout", headers=_csrf(client))

    assert missing.status_code == 403
    assert mismatched.status_code == 403
    assert non_ascii.status_code == 403
    assert accepted.status_code == 204


# --- WebSocket tickets -------------------------------------------------------


@requires_db
@pytest.mark.asyncio
async def test_ws_ticket_issue_is_single_use(db, redis_reset):
    async with _client() as client:
        await _signup(client, _email())
        me = await client.get("/api/v1/auth/me")
        response = await client.post("/api/v1/ws-ticket", headers=_csrf(client))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"ticket", "expires_in"}
    assert body["expires_in"] == get_settings().ws_ticket_ttl_seconds

    user_id = await service.redeem_ws_ticket(body["ticket"])
    assert user_id == uuid.UUID(me.json()["id"])
    assert await service.redeem_ws_ticket(body["ticket"]) is None


@requires_db
@pytest.mark.asyncio
async def test_ws_ticket_requires_a_session(db):
    async with _client() as client:
        response = await client.post("/api/v1/ws-ticket")
    assert response.status_code == 401
