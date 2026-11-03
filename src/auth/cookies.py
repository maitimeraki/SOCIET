"""Session + CSRF cookie helpers and the double-submit CSRF dependency."""

import secrets

from fastapi import HTTPException, Response
from starlette.requests import HTTPConnection

from src.config.settings import get_settings

SESSION_COOKIE = "sid"
CSRF_COOKIE = "csrf"
CSRF_HEADER = "X-CSRF-Token"

_STATE_CHANGING = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Endpoints a client may call before it has any cookie: the signup/login entry
# points and the token-bearing, pre-session lifecycle routes. Every other
# state-changing request must double-submit.
CSRF_EXEMPT_PATHS = frozenset(
    {
        "/api/v1/auth/signup",
        "/api/v1/auth/login",
        "/api/v1/auth/verify",
        "/api/v1/auth/reset/request",
        "/api/v1/auth/reset/confirm",
    }
)


def _cookie_max_age() -> int:
    return get_settings().session_ttl_days * 24 * 60 * 60


def set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        str(session_id),
        max_age=_cookie_max_age(),
        path="/",
        httponly=True,
        samesite="lax",
        secure=get_settings().cookie_secure,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        samesite="lax",
        secure=get_settings().cookie_secure,
    )


def set_csrf_cookie(response: Response) -> None:
    response.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(32),
        max_age=_cookie_max_age(),
        path="/",
        httponly=False,  # the SPA must read it to echo it back in the header
        samesite="lax",
        secure=get_settings().cookie_secure,
    )


def clear_csrf_cookie(response: Response) -> None:
    response.delete_cookie(
        CSRF_COOKIE, path="/", samesite="lax", secure=get_settings().cookie_secure
    )


def _tokens_match(header_token: str, cookie_token: str) -> bool:
    """Timing-safe comparison at the byte level.

    Our tokens are url-safe base64 (ASCII only). A non-ASCII value — both sides
    are client-controlled — fails closed: ``secrets.compare_digest`` raises
    TypeError on non-ASCII str, which would surface as a 500.
    """
    try:
        return secrets.compare_digest(
            header_token.encode("ascii"), cookie_token.encode("ascii")
        )
    except UnicodeEncodeError:
        return False


async def verify_csrf(request: HTTPConnection) -> None:
    """Double-submit check (plan §3) for state-changing requests.

    With a csrf cookie present, the X-CSRF-Token header must match it. Without
    one, only the signup/login entry points pass and a request carrying a
    session cookie is 403; a request with no session at all falls through to
    the endpoint's own auth (401), since there is no session to protect.

    Annotated ``HTTPConnection`` (not ``Request``) so the guard can sit at the
    router level on a router that also owns a WebSocket route: FastAPI then
    injects the connection for both, and the handshake — authenticated by
    ticket/sid, not a CSRF-able HTTP request — is skipped.
    """
    if request.scope.get("type") == "websocket":
        return
    if request.method not in _STATE_CHANGING:
        return

    cookie_token = request.cookies.get(CSRF_COOKIE)
    if not cookie_token:
        if request.url.path in CSRF_EXEMPT_PATHS:
            return
        if request.cookies.get(SESSION_COOKIE):
            raise HTTPException(
                status_code=403, detail="CSRF token missing or invalid."
            )
        return

    header_token = request.headers.get(CSRF_HEADER)
    if not header_token or not _tokens_match(header_token, cookie_token):
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid.")
