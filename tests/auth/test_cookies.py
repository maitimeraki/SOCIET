"""Cookie attribute and CSRF double-submit tests (no DB, no live server)."""

import uuid

import pytest
from fastapi import HTTPException
from fastapi.responses import Response
from starlette.requests import Request

from src.auth import cookies
from src.config.settings import Settings


def _response() -> Response:
    return Response()


def _request(
    method: str, path: str, *, cookies_: dict | None = None, headers: dict | None = None
) -> Request:
    # Header values travel as raw bytes and are decoded latin-1, so encode the
    # same way to reach the request with exactly the string a client sent.
    raw_headers = []
    if cookies_:
        raw_headers.append(
            (
                b"cookie",
                "; ".join(f"{k}={v}" for k, v in cookies_.items()).encode("latin-1"),
            )
        )
    for key, value in (headers or {}).items():
        raw_headers.append((key.lower().encode(), value.encode("latin-1")))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": raw_headers,
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
        }
    )


# --- cookie attributes ------------------------------------------------------


def test_session_cookie_is_httponly_lax_and_bounded():
    response = _response()
    cookies.set_session_cookie(response, uuid.uuid4())

    header = response.headers["set-cookie"].lower()
    assert "sid=" in header
    assert "httponly" in header
    assert "samesite=lax" in header
    assert "path=/" in header
    assert f"max-age={30 * 24 * 3600}" in header  # session_ttl_days default
    assert "secure" not in header  # cookie_secure default is False


def test_session_cookie_secure_flag_follows_settings(monkeypatch):
    monkeypatch.setattr(cookies, "get_settings", lambda: Settings(cookie_secure=True))

    response = _response()
    cookies.set_session_cookie(response, uuid.uuid4())

    assert "secure" in response.headers["set-cookie"].lower()


def test_secure_cookie_defaults_true_in_prod(monkeypatch):
    # Unset COOKIE_SECURE: the Secure flag follows ENV — True in prod only.
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    assert Settings(env="prod", email_api_key="test-key").cookie_secure is True
    assert Settings(env="dev").cookie_secure is False


def test_explicit_cookie_secure_beats_the_prod_default():
    assert (
        Settings(
            env="prod", cookie_secure=False, email_api_key="test-key"
        ).cookie_secure
        is False
    )


def test_clear_session_cookie_expires_it():
    response = _response()
    cookies.clear_session_cookie(response)

    header = response.headers["set-cookie"].lower()
    assert "sid=" in header
    assert "max-age=0" in header
    assert "path=/" in header


def test_csrf_cookie_is_readable_by_scripts():
    response = _response()
    cookies.set_csrf_cookie(response)

    header = response.headers["set-cookie"].lower()
    assert "csrf=" in header
    assert "httponly" not in header


# --- double-submit verification ---------------------------------------------


@pytest.mark.asyncio
async def test_safe_methods_pass_without_a_token():
    await cookies.verify_csrf(_request("GET", "/api/v1/auth/me"))


@pytest.mark.asyncio
async def test_websocket_handshake_is_skipped_not_500():
    # The guard sits at the router level on routers that also own a WebSocket
    # route; a WS scope has no "method", so it must be skipped before that read.
    from starlette.requests import HTTPConnection

    await cookies.verify_csrf(
        HTTPConnection(
            {"type": "websocket", "path": "/simulate/x/stream", "headers": []}
        )
    )


@pytest.mark.asyncio
async def test_session_without_a_csrf_cookie_is_403_outside_the_exempt_list():
    session_cookie = {"sid": str(uuid.uuid4())}

    with pytest.raises(HTTPException) as excinfo:
        await cookies.verify_csrf(
            _request("POST", "/api/v1/auth/logout", cookies_=session_cookie)
        )
    assert excinfo.value.status_code == 403

    await cookies.verify_csrf(
        _request("POST", "/api/v1/auth/signup", cookies_=session_cookie)
    )
    await cookies.verify_csrf(
        _request("POST", "/api/v1/auth/login", cookies_=session_cookie)
    )


@pytest.mark.asyncio
async def test_state_changing_request_with_no_session_passes_the_csrf_layer():
    # Nothing to protect: the endpoint's own auth dependency answers 401.
    await cookies.verify_csrf(_request("POST", "/api/v1/auth/logout"))
    await cookies.verify_csrf(_request("POST", "/api/v1/ws-ticket"))


@pytest.mark.asyncio
async def test_missing_or_mismatched_header_is_403_once_a_csrf_cookie_exists():
    with pytest.raises(HTTPException) as missing:
        await cookies.verify_csrf(
            _request("POST", "/api/v1/auth/logout", cookies_={"csrf": "tok"})
        )
    with pytest.raises(HTTPException) as mismatched:
        await cookies.verify_csrf(
            _request(
                "POST",
                "/api/v1/auth/logout",
                cookies_={"csrf": "tok"},
                headers={"X-CSRF-Token": "other"},
            )
        )
    assert missing.value.status_code == mismatched.value.status_code == 403


@pytest.mark.asyncio
async def test_non_ascii_tokens_are_403_not_500():
    # secrets.compare_digest raises TypeError on non-ASCII str; both values are
    # client-controlled, so the check must fail closed.
    with pytest.raises(HTTPException) as non_ascii_header:
        await cookies.verify_csrf(
            _request(
                "POST",
                "/api/v1/auth/logout",
                cookies_={"csrf": "tok"},
                headers={"X-CSRF-Token": "é"},
            )
        )
    with pytest.raises(HTTPException) as non_ascii_both:
        await cookies.verify_csrf(
            _request(
                "POST",
                "/api/v1/auth/logout",
                cookies_={"csrf": "é"},
                headers={"X-CSRF-Token": "é"},
            )
        )
    assert non_ascii_header.value.status_code == non_ascii_both.value.status_code == 403


@pytest.mark.asyncio
async def test_matching_header_passes():
    await cookies.verify_csrf(
        _request(
            "POST",
            "/api/v1/auth/logout",
            cookies_={"csrf": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
    )


@pytest.mark.asyncio
async def test_exempt_paths_still_need_the_header_when_a_csrf_cookie_exists():
    with pytest.raises(HTTPException) as excinfo:
        await cookies.verify_csrf(
            _request("POST", "/api/v1/auth/login", cookies_={"csrf": "tok"})
        )
    assert excinfo.value.status_code == 403
