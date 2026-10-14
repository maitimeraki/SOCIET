import json
import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from src.config.settings import get_settings

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """One JSON access-log object per request, carrying the correlation ID.

    The id comes from the ``X-Correlation-ID`` request header (or a fresh uuid4)
    and is echoed on the response so a client can join its logs to ours.
    Carrying it into queued job payloads (plan §10) lands with the queue.
    """

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        request.state.correlation_id = correlation_id

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            self._log(
                request, correlation_id, 500, start, level=logging.ERROR, exc_info=True
            )
            raise
        self._log(request, correlation_id, response.status_code, start)
        response.headers["X-Correlation-ID"] = correlation_id
        return response

    @staticmethod
    def _log(
        request: Request,
        correlation_id: str,
        status_code: int,
        start: float,
        level: int = logging.INFO,
        exc_info: bool = False,
    ) -> None:
        logger.log(
            level,
            json.dumps(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": logging.getLevelName(level),
                    "correlation_id": correlation_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                }
            ),
            extra={"correlation_id": correlation_id},
            exc_info=exc_info,
        )


def security_headers() -> dict[str, str]:
    """Hardening headers applied to every response; HSTS only off-dev (TLS is
    the proxy's job — plan §8). A CSP for the SPA belongs to the proxy too."""
    headers = {
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "X-Frame-Options": "DENY",
    }
    if get_settings().env != "dev":
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return headers


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.update(security_headers())
        return response
