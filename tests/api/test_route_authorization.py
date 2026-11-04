"""Task 15: the route-authorization inventory (plan §8, R23).

Every route on the real app is enumerated. A route is allowed to be public
only if it is named in the explicit allowlist below; every other HTTP route
must reach ``current_user`` in its dependency closure, every resource route
must reach ``require_owner``, and every WebSocket route must authenticate the
handshake with ``websocket_user``.

The inventory is a source check, so a negative self-check (a throwaway app with
one unguarded route) proves the helper actually fails when a guard is missing —
it cannot pass by checking nothing.
"""

import inspect

from fastapi import Depends, FastAPI, WebSocket
from starlette.routing import WebSocketRoute

from src.api.api_server import app
from src.auth.deps import current_user

# The explicit public allowlist (plan §8). Exact paths.
PUBLIC_PATHS = {
    "/health",
    "/ready",
    "/metrics",  # env-gated (METRICS_ENABLED); present only when enabled
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    # Signup/login/recovery are reachable before a session exists.
    "/api/v1/auth/signup",
    "/api/v1/auth/login",
    "/api/v1/auth/verify",
    "/api/v1/auth/reset/request",
    "/api/v1/auth/reset/confirm",
    # Terms/privacy must be readable before an account exists.
    "/api/v1/legal/documents",
    "/api/v1/legal/documents/{slug}",
    # Signature-authenticated by Stripe; no session, no CSRF, no degraded gate.
    "/api/v1/billing/webhook",
    # Retired legacy stubs: always 501, read nothing, write nothing (R20).
    "/simulate",
    "/simulate/async",
}

# A WebSocket route may be public only if named here (none are today).
PUBLIC_WS_PATHS: set[str] = set()


def _dependency_names(route) -> set[str]:
    """Callable names in the route's dependency closure, recursively."""
    names: set[str] = set()
    seen: set[int] = set()

    def walk(dependant) -> None:
        if dependant is None or id(dependant) in seen:
            return
        seen.add(id(dependant))
        call = getattr(dependant, "call", None)
        if call is not None:
            names.add(getattr(call, "__name__", repr(call)))
        for child in getattr(dependant, "dependencies", None) or ():
            walk(child)

    walk(getattr(route, "dependant", None))
    return names


def _http_routes(routes) -> list:
    return [route for route in routes if getattr(route, "methods", None)]


def _ws_routes(routes) -> list:
    return [route for route in routes if isinstance(route, WebSocketRoute)]


def _unguarded_http(routes) -> list[str]:
    """Non-public HTTP routes that never resolve ``current_user``."""
    return [
        route.path
        for route in _http_routes(routes)
        if route.path not in PUBLIC_PATHS
        and "current_user" not in _dependency_names(route)
    ]


def _unguarded_websockets(routes) -> list[str]:
    """Non-public WS routes whose handler never authenticates the socket."""
    return [
        route.path
        for route in _ws_routes(routes)
        if route.path not in PUBLIC_WS_PATHS
        and "websocket_user" not in inspect.getsource(route.endpoint)
    ]


def _unguarded_resources(routes) -> list[str]:
    """Non-public resource routes whose handler never calls ``require_owner``."""
    return [
        route.path
        for route in _http_routes(routes)
        if "{" in route.path
        and route.path not in PUBLIC_PATHS
        and "require_owner" not in inspect.getsource(route.endpoint)
    ]


def test_the_inventory_sees_the_real_app():
    assert len(_http_routes(app.routes)) > 20
    assert len(_ws_routes(app.routes)) >= 2
    assert any("{" in route.path for route in _http_routes(app.routes))


def test_every_non_public_http_route_reaches_current_user():
    assert _unguarded_http(app.routes) == []


def test_every_websocket_route_authenticates_the_handshake():
    assert _unguarded_websockets(app.routes) == []


def test_every_resource_route_enforces_ownership():
    resource_paths = [
        route.path
        for route in _http_routes(app.routes)
        if "{" in route.path and route.path not in PUBLIC_PATHS
    ]
    assert resource_paths  # the check is not vacuous
    assert _unguarded_resources(app.routes) == []


def test_the_allowlist_is_not_accidentally_stale():
    """Every allowlisted path that exists is actually public and unguarded.

    A path kept in the allowlist after gaining a guard would silently widen the
    public surface expectation; spell the mismatch out instead.
    """
    guarded = {
        route.path
        for route in _http_routes(app.routes)
        if route.path in PUBLIC_PATHS
        and "current_user" in _dependency_names(route)
    }
    assert guarded == set()


def test_the_helper_flags_a_missing_guard():
    """Negative self-check: an unguarded route must be reported."""
    probe = FastAPI()

    @probe.get("/unguarded")
    async def unguarded() -> dict:
        return {}

    @probe.get("/guarded")
    async def guarded(user=Depends(current_user)) -> dict:
        return {}

    assert _unguarded_http(probe.routes) == ["/unguarded"]


def test_the_helper_flags_a_missing_owner_guard():
    probe = FastAPI()

    @probe.get("/things/{thing_id}")
    async def unguarded(thing_id: str) -> dict:
        return {"id": thing_id}

    assert _unguarded_resources(probe.routes) == ["/things/{thing_id}"]


def test_the_helper_flags_an_unauthenticated_websocket():
    probe = FastAPI()

    @probe.websocket("/stream")
    async def open_socket(websocket: WebSocket) -> None:
        await websocket.accept()

    assert _unguarded_websockets(probe.routes) == ["/stream"]
