"""The uniform error contract (plan §6):
``{"error": {"code", "message", "correlation_id"}}`` on every failure.

The app under test mirrors the real middleware order: logging outermost (it
stamps the correlation id), then the security headers.
"""

import json
import logging
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from src.api.errors import CODE_BY_STATUS, install_error_handlers, payment_required
from src.api.middleware import LoggingMiddleware, SecurityHeadersMiddleware
from src.config.settings import Settings

CORRELATION_HEADER = "X-Correlation-ID"


class _Body(BaseModel):
    name: str


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(LoggingMiddleware)
    install_error_handlers(app)

    @app.get("/plain")
    async def plain():
        raise HTTPException(status_code=404, detail="No run with that id.")

    @app.get("/structured")
    async def structured():
        raise HTTPException(
            status_code=404,
            detail={"code": "run_not_found", "message": "No run with that id."},
        )

    @app.post("/validate")
    async def validate(body: _Body):
        return {"name": body.name}

    @app.get("/pay")
    async def pay():
        raise payment_required("Your plan's units are exhausted.")

    @app.get("/boom")
    async def boom():
        raise RuntimeError("kaboom")

    @app.get("/ok")
    async def ok():
        return {"ok": True}

    # The 500 is answered by ServerErrorMiddleware, which re-raises after
    # sending it — the client must not re-raise.
    return TestClient(app, raise_server_exceptions=False)


def _error(response) -> dict:
    assert set(response.json()) == {"error"}
    return response.json()["error"]


def test_unknown_route_is_404_in_the_uniform_shape():
    response = _client().get("/nope", headers={CORRELATION_HEADER: "cid-404"})
    assert response.status_code == 404
    assert _error(response) == {
        "code": "not_found",
        "message": "Not Found",
        "correlation_id": "cid-404",
    }


def test_plain_string_detail_maps_to_a_code_by_status():
    response = _client().get("/plain", headers={CORRELATION_HEADER: "cid-plain"})
    assert response.status_code == 404
    assert _error(response) == {
        "code": "not_found",
        "message": "No run with that id.",
        "correlation_id": "cid-plain",
    }


def test_structured_detail_sets_code_and_message_precisely():
    response = _client().get("/structured", headers={CORRELATION_HEADER: "cid-run"})
    assert response.status_code == 404
    assert _error(response) == {
        "code": "run_not_found",
        "message": "No run with that id.",
        "correlation_id": "cid-run",
    }


def test_validation_error_is_422_with_a_human_message(caplog):
    with caplog.at_level(logging.INFO, logger="src.api.errors"):
        response = _client().post(
            "/validate", json={"nope": 1}, headers={CORRELATION_HEADER: "cid-422"}
        )

    assert response.status_code == 422
    error = _error(response)
    assert error["code"] == "validation_error"
    assert error["message"] == "Request validation failed."
    assert error["correlation_id"] == "cid-422"
    # Field details are for operators, not the client.
    assert "name" in caplog.text
    assert "name" not in error["message"]


def test_payment_required_is_402_with_its_code():
    assert CODE_BY_STATUS[402] == "payment_required"

    response = _client().get("/pay", headers={CORRELATION_HEADER: "cid-402"})

    assert response.status_code == 402
    assert _error(response) == {
        "code": "payment_required",
        "message": "Your plan's units are exhausted.",
        "correlation_id": "cid-402",
    }


def test_unhandled_exception_is_500_internal_error():
    response = _client().get("/boom", headers={CORRELATION_HEADER: "cid-500"})
    assert response.status_code == 500
    assert _error(response) == {
        "code": "internal_error",
        "message": "Internal server error",
        "correlation_id": "cid-500",
    }


def test_correlation_id_is_generated_and_echoed_when_absent():
    response = _client().get("/plain")

    correlation_id = _error(response)["correlation_id"]
    assert uuid.UUID(correlation_id)  # parses
    assert response.headers[CORRELATION_HEADER] == correlation_id


def test_security_headers_are_on_success_and_error_responses():
    client = _client()

    for response in (client.get("/ok"), client.get("/plain")):
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "Strict-Transport-Security" not in response.headers  # env=dev


def test_hsts_is_sent_outside_dev(monkeypatch):
    from src.api import middleware

    monkeypatch.setattr(middleware, "get_settings", lambda: Settings(env="prod"))

    response = _client().get("/ok")

    assert response.headers["Strict-Transport-Security"] == (
        "max-age=31536000; includeSubDomains"
    )


def test_access_log_is_one_json_object_per_request(caplog):
    with caplog.at_level(logging.INFO, logger="src.api.middleware"):
        _client().get("/ok", headers={CORRELATION_HEADER: "cid-log"})

    record = next(r for r in caplog.records if r.name == "src.api.middleware")
    payload = json.loads(record.getMessage())

    assert payload["correlation_id"] == "cid-log"
    assert payload["method"] == "GET"
    assert payload["path"] == "/ok"
    assert payload["status_code"] == 200
    assert payload["level"] == "INFO"
    assert payload["duration_ms"] >= 0
    assert payload["timestamp"].startswith("20")
