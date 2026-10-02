"""Phase-4 boot smoke: the API app imports and the debate routes are registered.

Import-only, deliberately: the app's lifespan needs a live Neo4j, so it is NOT
executed here — the lifespan boot and the seeded-graph end-to-end job are
pending-live items (P4-D report, deliverable C). The delivered payload itself
is already covered by `tests/api/test_debate_api.py::TestDebateJobPayload`.
"""
from fastapi import FastAPI
from starlette.routing import WebSocketRoute

from src.api.api_server import app


def _routes_by_path() -> dict:
    return {route.path: route for route in app.routes if getattr(route, "path", None)}


def test_app_imports_with_the_debate_routes_registered():
    assert isinstance(app, FastAPI)

    paths = set(_routes_by_path())
    assert {"/simulate/debate", "/simulate/{job_id}", "/simulate/{job_id}/stream"} <= paths


def test_debate_routes_keep_their_methods():
    routes = _routes_by_path()

    assert "POST" in routes["/simulate/debate"].methods
    assert "GET" in routes["/simulate/{job_id}"].methods
    assert isinstance(routes["/simulate/{job_id}/stream"], WebSocketRoute)
