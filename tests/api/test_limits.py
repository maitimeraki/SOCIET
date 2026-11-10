"""Request gates: JSON body cap, degraded-service gate, rate limiting."""

import uuid

import pydantic
import pytest
from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.testclient import TestClient
from starlette.requests import Request

from src.api.auth_api import router as auth_router
from src.api.errors import install_error_handlers
from src.api.limits import (
    JSONBodySizeLimitMiddleware,
    _storage_uri,
    build_limiter,
    client_key,
    install_rate_limiter,
    service_available,
)
from src.auth import service
from src.config.settings import Settings, get_settings
from src.db.engine import get_db

LOGIN = {
    "email": "rate-limit-test@example.com",
    "password": "hunter2hunter2",
    "accept_terms": True,
    "age_confirmed": True,
}


def _capped_app() -> tuple[FastAPI, list]:
    """A tiny app behind the body cap; ``parsed`` records handler entry."""
    app = FastAPI()
    app.add_middleware(JSONBodySizeLimitMiddleware)
    install_error_handlers(app)
    parsed: list = []

    @app.post("/json")
    async def json_route(payload: dict):
        parsed.append(payload)
        return {"parsed": True}

    @app.post("/upload")
    async def upload_route(files: list[UploadFile]):
        return {"count": len(files)}

    return app, parsed


@pytest.fixture
def small_json_cap(monkeypatch):
    monkeypatch.setenv("MAX_JSON_BYTES", "1024")
    get_settings.cache_clear()
    yield 1024
    get_settings.cache_clear()


def test_oversized_json_body_is_rejected_before_parsing(small_json_cap):
    app, parsed = _capped_app()

    response = TestClient(app).post("/json", json={"blob": "x" * 2048})

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"
    assert parsed == []  # never reached the route


def test_json_body_within_the_cap_passes(small_json_cap):
    app, parsed = _capped_app()

    response = TestClient(app).post("/json", json={"ok": "x" * 16})

    assert response.status_code == 200
    assert len(parsed) == 1


def test_multipart_uploads_keep_their_own_gate(small_json_cap):
    """The cap is JSON-only: ingest keeps its 5 MB / 20-file multipart gate."""
    app, _ = _capped_app()

    response = TestClient(app).post(
        "/upload", files=[("files", ("big.txt", b"x" * 4096, "text/plain"))]
    )

    assert response.status_code == 200


def test_real_app_caps_the_body_before_routing():
    from src.api.api_server import app

    # /health is GET-only: a 405 here would mean the request reached the router.
    response = TestClient(app).post("/health", json={"blob": "x" * 1_100_000})

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_service_available_gate_is_503_while_degraded():
    app = FastAPI()
    install_error_handlers(app)

    @app.post("/enqueue", dependencies=[Depends(service_available)])
    async def enqueue():
        return {"queued": True}

    client = TestClient(app)
    app.state.degraded = True
    degraded = client.post("/enqueue")

    app.state.degraded = False
    healthy = client.post("/enqueue")

    assert degraded.status_code == 503
    assert degraded.json()["error"]["code"] == "service_unavailable"
    assert healthy.status_code == 200


def test_login_rate_limit_is_429_with_retry_after(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_LOGIN", "2/minute")
    get_settings.cache_clear()

    async def _no_db():
        return None

    async def _reject_login(*args, **kwargs):
        raise HTTPException(status_code=401, detail=service.INVALID_CREDENTIALS)

    monkeypatch.setattr("src.api.auth_api.service.login", _reject_login)

    app = FastAPI()
    install_error_handlers(app)
    install_rate_limiter(app)
    app.include_router(auth_router)
    app.dependency_overrides[get_db] = _no_db
    client = TestClient(app)

    try:
        responses = [client.post("/api/v1/auth/login", json=LOGIN) for _ in range(3)]
    finally:
        get_settings.cache_clear()

    # The first two reach the handler; the third never does.
    assert [r.status_code for r in responses] == [401, 401, 429]
    assert responses[0].json()["error"]["code"] == "unauthorized"

    error = responses[2].json()["error"]
    assert error["code"] == "rate_limited"
    assert uuid.UUID(error["correlation_id"])
    assert responses[2].headers["Retry-After"] == "60"


def _request(peer: str | None, forwarded: str | None = None) -> Request:
    headers = [] if forwarded is None else [(b"x-forwarded-for", forwarded.encode())]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
        "client": (peer, 1234) if peer else None,
    }
    return Request(scope)


def _allow_forwarded(monkeypatch, value: str) -> None:
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", value)
    get_settings.cache_clear()


def test_client_key_without_forwarded_header_uses_the_peer(monkeypatch):
    _allow_forwarded(monkeypatch, "*")

    assert client_key(_request("10.0.0.1")) == "10.0.0.1"


def test_client_key_trusts_forwarded_header_from_an_allowed_peer(monkeypatch):
    _allow_forwarded(monkeypatch, "10.0.0.1")

    request = _request("10.0.0.1", "1.2.3.4, 203.0.113.9")

    # The trusted proxy appended the real client; the leftmost value is spoofable.
    assert client_key(request) == "203.0.113.9"


def test_client_key_matches_a_peer_inside_an_allowed_cidr(monkeypatch):
    _allow_forwarded(monkeypatch, "10.0.0.0/8")

    assert client_key(_request("10.1.2.3", "203.0.113.9")) == "203.0.113.9"


def test_client_key_rejects_a_peer_outside_an_allowed_cidr(monkeypatch):
    _allow_forwarded(monkeypatch, "192.168.0.0/16")

    assert client_key(_request("10.1.2.3", "203.0.113.9")) == "10.1.2.3"


def test_client_key_exact_matches_a_non_ip_peer(monkeypatch):
    """TestClient's peer is the literal host "testclient", not an IP."""
    _allow_forwarded(monkeypatch, "testclient")

    assert client_key(_request("testclient", "203.0.113.9")) == "203.0.113.9"


def test_client_key_ignores_forwarded_header_from_an_untrusted_peer(monkeypatch):
    _allow_forwarded(monkeypatch, "192.0.2.1")

    request = _request("10.0.0.1", "203.0.113.9")

    assert client_key(request) == "10.0.0.1"


def test_client_key_wildcard_trusts_any_peer(monkeypatch):
    _allow_forwarded(monkeypatch, "*")

    assert client_key(_request("10.0.0.1", "203.0.113.9")) == "203.0.113.9"


def test_storage_uri_prefers_the_explicit_setting_over_redis_url(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("RATE_LIMIT_STORAGE_URI", "memory://")
    get_settings.cache_clear()

    assert _storage_uri() == "memory://"


def test_build_limiter_uses_the_given_or_default_storage(monkeypatch):
    memory = build_limiter("memory://")

    # An ambient RATE_LIMIT_STORAGE_URI (the documented test opt-out) would
    # otherwise win over REDIS_URL.
    monkeypatch.delenv("RATE_LIMIT_STORAGE_URI", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    get_settings.cache_clear()
    redis_backed = build_limiter()

    assert memory._storage_uri == "memory://"
    assert redis_backed._storage_uri == "redis://localhost:6379/0"


def test_settings_are_immutable_after_construction():
    settings = Settings()

    with pytest.raises((pydantic.ValidationError, TypeError)):
        settings.billing_enabled = True


def test_signup_has_its_own_setting(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_SIGNUP", "1/hour")
    get_settings.cache_clear()

    async def _no_db():
        return None

    async def _reject_signup(*args, **kwargs):
        raise HTTPException(
            status_code=409, detail="An account with this email already exists."
        )

    monkeypatch.setattr("src.api.auth_api.service.signup", _reject_signup)

    app = FastAPI()
    install_error_handlers(app)
    install_rate_limiter(app)
    app.include_router(auth_router)
    app.dependency_overrides[get_db] = _no_db
    client = TestClient(app)

    try:
        first = client.post("/api/v1/auth/signup", json=LOGIN)
        second = client.post("/api/v1/auth/signup", json=LOGIN)
    finally:
        get_settings.cache_clear()

    assert (first.status_code, second.status_code) == (409, 429)
    assert second.headers["Retry-After"] == "3600"
