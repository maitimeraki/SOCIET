"""Request gates: JSON body cap, degraded-service gate, rate limiting.

Rate limits are settings-driven (``RATE_LIMIT_*`` env vars) and read through
callables, so a test can override the env and ``get_settings.cache_clear()``
without rebuilding the routes.
"""

import ipaddress

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import HTTPConnection

from src.api.errors import error_response
from src.config.settings import get_settings


def _is_trusted_peer(peer: str, allowed: list[str]) -> bool:
    """Exact address, CIDR network, or ``*`` — non-IP peers fall back to exact."""
    for entry in allowed:
        if entry == "*" or entry == peer:
            return True
        try:
            if ipaddress.ip_address(peer) in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            # Non-IP peer or non-network entry: exact matching above is all.
            continue
    return False


def client_key(request: HTTPConnection) -> str:
    """Bucket identity: the forwarded client IP only when our peer is trusted.

    ``X-Forwarded-For`` is client-controlled; accepting it from any peer would
    let a caller mint a fresh bucket per request. Trust is therefore opt-in via
    ``FORWARDED_ALLOW_IPS`` — the proxy address, a network, or ``*``.

    Assumption: the immediate trusted proxy appends (or overwrites) the client
    IP, so we take the last hop. The leftmost entries are whatever a client
    chose to send and must not be believed.
    """
    peer = request.client.host if request.client else ""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and _is_trusted_peer(peer, get_settings().forwarded_allow_ips):
        return forwarded.split(",")[-1].strip() or peer or "unknown"
    return peer or "unknown"


def _storage_uri() -> str:
    settings = get_settings()
    return settings.rate_limit_storage_uri or settings.redis_url


def build_limiter(storage_uri: str | None = None) -> Limiter:
    uri = storage_uri or _storage_uri()
    # key_style="endpoint": the bucket scope is the handler, not the path — so
    # the legacy and /api/v1 mounts of one route share a budget instead of
    # doubling it.
    return Limiter(key_func=client_key, key_style="endpoint", storage_uri=uri)


# Redis-backed by default (shared across replicas); RATE_LIMIT_STORAGE_URI=
# memory:// opts a single-process/test deployment out.
limiter = build_limiter()


class JSONBodySizeLimitMiddleware(BaseHTTPMiddleware):
    """413 for ``application/json`` bodies over ``MAX_JSON_BYTES``, before the
    body is parsed. Multipart keeps its own per-file gate (ingest_api)."""

    async def dispatch(self, request: Request, call_next):
        content_type = (
            request.headers.get("content-type", "").split(";")[0].strip().lower()
        )
        declared = request.headers.get("content-length", "")
        if content_type == "application/json" and declared.isdigit():
            max_bytes = get_settings().max_json_bytes
            if int(declared) > max_bytes:
                return error_response(
                    413,
                    "payload_too_large",
                    f"JSON body exceeds the {max_bytes} byte limit.",
                    request,
                )
        # ponytail: chunked bodies declare no length and stream through — a
        # counting reader can cap them if a client ever actually does that.
        return await call_next(request)


async def service_available(request: Request) -> None:
    """Dependency gate for enqueue endpoints: 503 while the app is degraded
    (no LLM at boot), so reads keep working but new work is refused."""
    if getattr(request.app.state, "degraded", False):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "service_unavailable",
                "message": "The service is temporarily unable to accept new work.",
            },
        )


async def rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> JSONResponse:
    limit = getattr(exc, "limit", None)
    retry_after = None
    if limit is not None and getattr(limit, "limit", None) is not None:
        # The window length — an upper bound on the wait (limits.RateLimitItem).
        retry_after = str(limit.limit.get_expiry())
    return error_response(
        429,
        "rate_limited",
        "Rate limit exceeded. Try again later.",
        request,
        headers={"Retry-After": retry_after} if retry_after else None,
    )


def install_rate_limiter(app: FastAPI) -> None:
    app.state.limiter = limiter
    # Starlette types the handler against the base `Exception`; this handler is
    # deliberately narrowed to RateLimitExceeded.
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore[arg-type]
