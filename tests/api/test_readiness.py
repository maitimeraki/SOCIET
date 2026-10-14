"""/health vs /ready (plan §9), plus the real app's edge wiring:
env-driven CORS, trusted hosts, security headers.
"""

import asyncio
import os
import sys
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from src.api import api_server
from src.api.api_server import _postgres_ok, _redis_ok, app
from src.config.settings import get_settings
from src.db.engine import get_engine

if sys.platform == "win32":
    # psycopg refuses to run async on the default ProactorEventLoop (same
    # guard as tests/db/conftest.py).
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture
def app_state():
    """`app` is a module singleton; restore the probe flags after each test."""
    saved = {
        key: getattr(app.state, key, None) for key in ("degraded", "last_llm_probe_at")
    }
    yield app
    for key, value in saved.items():
        setattr(app.state, key, value)


def _stub(value: bool):
    async def _check() -> bool:
        return value

    return _check


def test_health_is_200_and_public(app_state):
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_health_carries_the_security_headers(app_state):
    headers = TestClient(app).get("/health").headers

    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "Strict-Transport-Security" not in headers  # env=dev


def test_ready_is_503_with_the_contract_while_degraded(app_state):
    app.state.degraded = True
    app.state.last_llm_probe_at = time.monotonic()  # trust the cached verdict

    response = TestClient(app).get("/ready")

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "service_unavailable"
    assert error["message"] == "LLM provider is not reachable."
    assert uuid.UUID(error["correlation_id"])
    assert response.headers["X-Correlation-ID"] == error["correlation_id"]


def test_ready_reprobes_once_the_cached_verdict_is_stale(app_state, monkeypatch):
    probed = []

    async def _probe(_app):
        probed.append(True)
        _app.state.degraded = False
        _app.state.last_llm_probe_at = time.monotonic()
        return True

    monkeypatch.setattr(api_server, "_probe_llm", _probe)
    monkeypatch.setattr(api_server, "_postgres_ok", _stub(True))
    monkeypatch.setattr(api_server, "_redis_ok", _stub(True))
    app.state.degraded = True
    app.state.last_llm_probe_at = time.monotonic() - api_server._PROBE_CACHE_SECONDS - 1

    response = TestClient(app).get("/ready")

    assert probed == [True]
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_names_the_unreachable_dependency(app_state, monkeypatch):
    async def _probe(_app):
        _app.state.degraded = False
        _app.state.last_llm_probe_at = time.monotonic()
        return True

    monkeypatch.setattr(api_server, "_probe_llm", _probe)
    monkeypatch.setattr(api_server, "_postgres_ok", _stub(False))
    monkeypatch.setattr(api_server, "_redis_ok", _stub(True))

    response = TestClient(app).get("/ready")

    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Database is not reachable."


@pytest.mark.asyncio
async def test_ready_is_200_when_dependencies_are_reachable(app_state):
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set")
    if not await _postgres_ok():
        pytest.skip("Postgres is not reachable")
    if not await _redis_ok():
        pytest.skip("Redis is not reachable")
    app.state.degraded = False
    app.state.last_llm_probe_at = time.monotonic()  # no live LLM probe needed

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.get("/ready")
    finally:
        await get_engine().dispose()

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_cors_echoes_only_configured_origins(app_state):
    allowed = get_settings().cors_allowed_origins[0]
    client = TestClient(app)

    allowed_response = client.get("/health", headers={"Origin": allowed})
    blocked_response = client.get("/health", headers={"Origin": "https://evil.example"})

    assert allowed_response.headers["access-control-allow-origin"] == allowed
    assert "access-control-allow-origin" not in blocked_response.headers


def test_untrusted_host_is_rejected(app_state):
    response = TestClient(app).get("/health", headers={"Host": "evil.example"})

    assert response.status_code == 400
