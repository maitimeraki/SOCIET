"""Request gates: JSON body cap, degraded-service gate, rate limiting.

Rate limits are settings-driven (``RATE_LIMIT_*`` env vars) and read through
callables, so a test can override the env and ``get_settings.cache_clear()``
without rebuilding the routes.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.errors import error_response
from src.config.settings import get_settings

# Process-local limits, keyed by client IP. A shared Redis store is the swap
# for multi-replica deployments (plan §6).
# key_style="endpoint": the bucket scope is the handler, not the path — so the
# legacy and /api/v1 mounts of one route share a budget instead of doubling it.
limiter = Limiter(key_func=get_remote_address, key_style="endpoint")


class JSONBodySizeLimitMiddleware(BaseHTTPMiddleware):
    """413 for ``application/json`` bodies over ``MAX_JSON_BYTES``, before the
    body is parsed. Multipart keeps its own per-file gate (ingest_api)."""

    async def dispatch(self, request: Request, call_next):
        content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
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
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
