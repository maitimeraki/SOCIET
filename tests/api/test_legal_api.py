"""HTTP-level legal document and consent routes (task 9).

A minimal app mounts only the auth and legal routers: the real api_server
lifespan probes Neo4j and a live LLM, which is out of scope here.
"""

import asyncio
import os
import sys
import uuid

import pytest
from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.api.auth_api import router as auth_router
from src.api.errors import install_error_handlers
from src.api.legal_api import router as legal_router
from src.auth.cookies import CSRF_COOKIE, CSRF_HEADER
from src.config.settings import get_settings
from src.db.models import UserConsent
from src.legal import registry

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)

PASSWORD = "hunter2hunter2"

_app = FastAPI()
install_error_handlers(_app)
_app.add_middleware(TrustedHostMiddleware, allowed_hosts=["testserver"])
_app.include_router(auth_router)
_app.include_router(legal_router)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=_app), base_url="http://testserver")


def _email() -> str:
    return f"auth-test-legal-{uuid.uuid4().hex[:10]}@example.com"


def _csrf(client: AsyncClient) -> dict:
    return {CSRF_HEADER: client.cookies.get(CSRF_COOKIE)}


async def _signup(client: AsyncClient) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup", json={"email": _email(), "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


@requires_db
@pytest.mark.asyncio
async def test_documents_list_is_public_and_lists_four_slugs(db):
    async with _client() as client:
        response = await client.get("/api/v1/legal/documents")

    assert response.status_code == 200
    body = response.json()
    assert [item["slug"] for item in body] == sorted(
        seed.slug for seed in registry.SEEDS
    )
    assert len(body) == 4


@requires_db
@pytest.mark.asyncio
async def test_document_detail_renders_contact_and_unknown_slug_is_404(db):
    async with _client() as client:
        response = await client.get("/api/v1/legal/documents/privacy")
        missing = await client.get("/api/v1/legal/documents/does-not-exist")

    assert response.status_code == 200
    body = response.json()
    assert body["slug"] == "privacy"
    assert body["content"].startswith("> Draft for counsel review.")
    assert "{{" not in body["content"]

    contact = get_settings().legal_contact_email.strip() or "hello@societas.app"
    assert contact in body["content"]

    assert missing.status_code == 404


@requires_db
@pytest.mark.asyncio
async def test_consent_requires_session_then_csrf_and_records_two_rows(db):
    async with _client() as anonymous:
        unauthenticated = await anonymous.post("/api/v1/legal/consent")
    assert unauthenticated.status_code == 401

    async with _client() as client:
        user_id = await _signup(client)

        without_csrf = await client.post("/api/v1/legal/consent")
        assert without_csrf.status_code == 403

        accepted = await client.post("/api/v1/legal/consent", headers=_csrf(client))
        assert accepted.status_code == 200
        assert accepted.json() == {"accepted": ["terms", "privacy"]}

    rows = (
        (await db.execute(select(UserConsent).where(UserConsent.user_id == user_id)))
        .scalars()
        .all()
    )
    assert len(rows) == 2
