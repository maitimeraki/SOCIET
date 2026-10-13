"""Uniform error contract (plan §6).

Every failure leaves the API as::

    {"error": {"code": "run_not_found", "message": "No run with that id.",
               "correlation_id": "…"}}

`HTTPException` raised with a plain string detail gets a code by status;
raising with ``detail={"code": …, "message": …}`` sets both precisely (the
mechanism the route layer uses for names like ``run_not_found``).
"""

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from src.api.middleware import security_headers

logger = logging.getLogger(__name__)

CODE_BY_STATUS: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    503: "service_unavailable",
}
# Statuses outside the map (405, 502, …) keep their detail text under this code.
FALLBACK_CODE = "http_error"


def correlation_id_of(request: Request | None) -> str:
    """The id the logging middleware stamped on the request, or a fresh one."""
    return (
        getattr(getattr(request, "state", None), "correlation_id", None) or str(uuid.uuid4())
    )


def error_response(
    status_code: int,
    code: str,
    message: str,
    request: Request | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """The one response shape for failures. Middleware calls this directly:
    an exception raised in middleware never reaches the handlers below."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "correlation_id": correlation_id_of(request),
            }
        },
        headers=headers,
    )


def _code_and_message(exc: HTTPException) -> tuple[str, str]:
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        return str(detail["code"]), str(detail["message"])
    return CODE_BY_STATUS.get(exc.status_code, FALLBACK_CODE), str(detail)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code, message = _code_and_message(exc)
    return error_response(exc.status_code, code, message, request, headers=exc.headers)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Field details are for operators; the client gets a generic message. `input`
    # and `ctx` are dropped — they can carry the raw body (passwords).
    details = [
        {"loc": error.get("loc"), "msg": error.get("msg"), "type": error.get("type")}
        for error in exc.errors()
    ]
    logger.info(
        "Request validation failed for %s %s: %s",
        request.method,
        request.url.path,
        details,
        extra={"correlation_id": correlation_id_of(request)},
    )
    return error_response(422, "validation_error", "Request validation failed.", request)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled exception: %s",
        exc,
        extra={"correlation_id": correlation_id_of(request)},
    )
    # This handler answers from ServerErrorMiddleware, outside the middleware
    # stack — so the response needs the security headers set here.
    return error_response(
        500,
        "internal_error",
        "Internal server error",
        request,
        headers=security_headers(),
    )


def install_error_handlers(app: FastAPI) -> None:
    # Registered on Starlette's HTTPException — the base of FastAPI's, and the
    # class the router raises for an unmatched path.
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
