"""HTTP account lifecycle: signup consent/age, verification, password reset."""

import asyncio
import os
import sys
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from src.api.auth_api import router as auth_router
from src.api.errors import install_error_handlers
from src.auth import reset, service, verify
from src.auth.cookies import CSRF_COOKIE, CSRF_HEADER
from src.db.models import LegalDocument, User, UserConsent, UserSession

if sys.platform == "win32":
    # psycopg refuses to run async on the default ProactorEventLoop.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)


def _redis_available() -> bool:
    try:
        import redis

        from src.config.settings import get_settings

        client = redis.Redis.from_url(
            get_settings().redis_url, socket_connect_timeout=1
        )
        try:
            return bool(client.ping())
        finally:
            client.close()
    except Exception:
        return False


requires_redis = pytest.mark.skipif(
    not _redis_available(), reason="Redis is not reachable"
)

PASSWORD = "hunter2hunter2"
NEW_PASSWORD = "brand-new-password"

_app = FastAPI()
install_error_handlers(_app)
_app.include_router(auth_router)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=_app), base_url="http://testserver")


def _email() -> str:
    return f"auth-test-{uuid.uuid4().hex[:10]}@example.com"


def _csrf(client: AsyncClient) -> dict:
    return {CSRF_HEADER: client.cookies.get(CSRF_COOKIE)}


def _signup_body(email: str) -> dict:
    return {
        "email": email,
        "password": PASSWORD,
        "accept_terms": True,
        "age_confirmed": True,
    }


async def _signup(client: AsyncClient, email: str | None = None):
    response = await client.post(
        "/api/v1/auth/signup", json=_signup_body(email or _email())
    )
    assert response.status_code == 201, response.text
    return response


@requires_db
@pytest.mark.asyncio
async def test_signup_without_consent_or_age_creates_no_account(db):
    bodies = [
        {"email": _email(), "password": PASSWORD},
        {**_signup_body(_email()), "age_confirmed": False},
        {**_signup_body(_email()), "accept_terms": False},
    ]

    async with _client() as client:
        responses = [
            await client.post("/api/v1/auth/signup", json=body) for body in bodies
        ]

    assert [response.status_code for response in responses] == [422, 422, 422]
    count = (
        await db.execute(
            select(func.count())
            .select_from(User)
            .where(User.email.in_([body["email"] for body in bodies]))
        )
    ).scalar_one()
    assert count == 0


@requires_db
@pytest.mark.asyncio
async def test_signup_records_age_and_both_consents(db):
    email = _email()
    async with _client() as client:
        await _signup(client, email)

    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    assert user.age_confirmed_at is not None
    assert user.email_verified_at is None

    slugs = (
        (
            await db.execute(
                select(LegalDocument.slug)
                .join(UserConsent, UserConsent.document_id == LegalDocument.id)
                .where(UserConsent.user_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    assert sorted(slugs) == ["privacy", "terms"]


@requires_db
@requires_redis
@pytest.mark.asyncio
async def test_verify_send_requires_auth_and_csrf(db, redis_reset):
    async with _client() as anonymous:
        unauthenticated = await anonymous.post("/api/v1/auth/verify/send")

    async with _client() as client:
        await _signup(client)
        missing_csrf = await client.post("/api/v1/auth/verify/send")
        accepted = await client.post("/api/v1/auth/verify/send", headers=_csrf(client))

    assert unauthenticated.status_code == 401
    assert missing_csrf.status_code == 403
    assert accepted.status_code == 204


@requires_db
@requires_redis
@pytest.mark.asyncio
async def test_verify_route_sets_email_verified_at(db, redis_reset):
    async with _client() as client:
        response = await _signup(client)
    user_id = uuid.UUID(response.json()["id"])
    token = await verify.issue_verification_token(user_id)

    async with _client() as fresh:
        first = await fresh.post("/api/v1/auth/verify", json={"token": token})
    async with _client() as replay:
        second = await replay.post("/api/v1/auth/verify", json={"token": token})

    assert first.status_code == 204
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "invalid_token"

    user = await db.get(User, user_id)
    await db.refresh(user)
    assert user.email_verified_at is not None


@requires_db
@pytest.mark.asyncio
async def test_reset_request_is_enumeration_safe(db, monkeypatch):
    email = _email()
    user, _ = await service.signup(
        db, email, PASSWORD, accept_terms=True, age_confirmed=True
    )

    issued: list[uuid.UUID] = []

    async def _spy(user_id: uuid.UUID) -> str:
        issued.append(user_id)
        return "spy-token"

    monkeypatch.setattr(reset, "issue_reset_token", _spy)

    async with _client() as client:
        known = await client.post("/api/v1/auth/reset/request", json={"email": email})
        unknown = await client.post(
            "/api/v1/auth/reset/request", json={"email": _email()}
        )

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json() == {"status": "accepted"}
    assert issued == [user.id]


@requires_db
@requires_redis
@pytest.mark.asyncio
async def test_reset_confirm_changes_password_and_revokes_sessions(db, redis_reset):
    email = _email()
    async with _client() as first_device:
        response = await _signup(first_device, email)
    async with _client() as second_device:
        assert (
            await second_device.post(
                "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
            )
        ).status_code == 200

    user_id = uuid.UUID(response.json()["id"])
    token = await reset.issue_reset_token(user_id)

    async with _client() as fresh:
        short = await fresh.post(
            "/api/v1/auth/reset/confirm",
            json={"token": token, "new_password": "short"},
        )
        confirmed = await fresh.post(
            "/api/v1/auth/reset/confirm",
            json={"token": token, "new_password": NEW_PASSWORD},
        )

    assert short.status_code == 422
    assert confirmed.status_code == 204

    sessions = (
        (await db.execute(select(UserSession).where(UserSession.user_id == user_id)))
        .scalars()
        .all()
    )
    assert len(sessions) == 2
    assert all(row.revoked_at is not None for row in sessions)

    async with _client() as old:
        assert (
            await old.post(
                "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
            )
        ).status_code == 401
    async with _client() as current:
        assert (
            await current.post(
                "/api/v1/auth/login",
                json={"email": email, "password": NEW_PASSWORD},
            )
        ).status_code == 200


@requires_db
@requires_redis
@pytest.mark.asyncio
async def test_token_routes_pass_without_csrf_cookie_or_header(db, redis_reset):
    async with _client() as client:
        verify_response = await client.post(
            "/api/v1/auth/verify", json={"token": "never-issued"}
        )
        request_response = await client.post(
            "/api/v1/auth/reset/request", json={"email": _email()}
        )
        confirm_response = await client.post(
            "/api/v1/auth/reset/confirm",
            json={"token": "never-issued", "new_password": NEW_PASSWORD},
        )

    assert verify_response.status_code == 400
    assert request_response.status_code == 202
    assert confirm_response.status_code == 400
