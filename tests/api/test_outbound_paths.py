"""Route coverage for the outbound boundary (spec 4a, 4b, 5; audit L-G4).

Every route whose path names run, agent, debate or graph-job data is classified here:
DATA_ROUTES maps it to the leak-harness test that drives its projection, NO_DATA_ROUTES to the
reason its body carries no run data. A new route that matches RUN_DATA_PATH fails until it is
classified, so it cannot reach a client unreviewed. The leak cases stay in the named harness
tests; this file checks the inventory, not the bodies.
"""
import ast
import re
from pathlib import Path

import pytest

from src.api import public_events
from src.api.api_server import app

REPO = Path(__file__).resolve().parents[2]
RUN_DATA_PATH = re.compile(r"simulate|debates?/|/jobs/|operator/runs|account/export")
MOUNT_PREFIX = "/api/v1"

#: spec 4b: never shown to a client. No allowlist may carry one of these as a key.
FORBIDDEN_4B_KEYS = frozenset({
    "evidence", "evidence_id", "evidence_items", "evidence_quote", "quote", "quotes",
    "document_title", "section", "sections", "span", "spans", "chunk_id", "chunk_ids",
    "cite_id", "cite_ids", "cite_marker", "cite_markers", "validation", "validation_results",
    "rejected_claims", "similarity", "rank_features", "features", "prompt_version",
    "model_version", "dossier_hash", "version_hash", "source_count", "unknown",
})

DATA_ROUTES: dict[tuple[str, str], tuple[str, str]] = {
    ("GET", "/simulate/debates"): (
        "tests/api/test_jobs_api.py", "test_the_debate_list_only_contains_the_callers_runs"),
    ("GET", "/simulate/debates/{run_id}"): (
        "tests/api/test_public_events.py", "test_get_debate_doc_projects_stored_events_and_result"),
    ("GET", "/simulate/debates/{run_id}/roster"): (
        "tests/api/test_roster_api.py", "test_roster_returns_only_the_view_keys"),
    ("GET", "/simulate/debates/{run_id}/sources/{n}"): (
        "tests/api/test_roster_api.py", "test_the_source_response_has_exactly_three_keys"),
    ("GET", "/simulate/debates/{run_id}/graph"): (
        "tests/api/test_debate_graph_route.py", "test_owned_run_returns_five_fields"),
    ("GET", "/simulate/{job_id}"): (
        "tests/api/test_jobs_api.py",
        "test_a_debate_job_read_through_the_api_never_serves_its_backend_only_keys"),
    ("WS", "/simulate/{job_id}/stream"): (
        "tests/api/test_public_events.py",
        "test_broadcast_persists_and_sends_only_the_projected_event"),
    ("WS", "/simulate/{job_id}/graph_stream"): (
        "tests/api/test_graph_ws.py", "test_first_frame_is_snapshot_then_deltas_vocabulary_and_done"),
    ("GET", "/simulate/jobs/{job_id}"): (
        "tests/api/test_jobs_projection.py", "test_get_job_serves_no_result_for_an_unlisted_mode"),
    ("GET", "/jobs/{job_id}"): (
        "tests/api/test_jobs_projection.py", "test_get_job_serves_no_result_for_an_unlisted_mode"),
    ("POST", "/account/export"): (
        "tests/api/test_public_events.py", "test_debate_run_export_verdict_is_projected"),
    ("GET", "/operator/runs/{run_id}/agents/{node_id}"): (
        "tests/api/test_roster_api.py", "test_operator_roles_can_read_and_the_read_is_audited"),
}

#: Run-data-shaped routes whose body holds no run data: an id and a status, or a 501.
NO_DATA_ROUTES: dict[tuple[str, str], str] = {
    ("POST", "/simulate"): "retired: answers 501 with a message, no run data",
    ("POST", "/simulate/async"): "retired: answers 501 with a message, no run data",
    ("POST", "/simulate/debate"): "enqueues a debate; the body is the job id and status",
    ("POST", "/simulate/debates/{run_id}/verdict/retry"): "enqueues a verdict job; the body is the job id",
    ("POST", "/simulate/ontology"): "enqueues a graph job; the body is the job id",
    ("POST", "/simulate/build_graph"): "enqueues a graph job; the body is the job id",
    ("POST", "/simulate/normalize_graph"): "enqueues a graph job; the body is the job id",
    ("DELETE", "/simulate/jobs/{job_id}"): "cancels a job; the body is {job_id, status}",
    ("DELETE", "/jobs/{job_id}"): "cancels a job; the body is {job_id, status}",
}


def _canonical(path: str) -> str:
    return path[len(MOUNT_PREFIX):] if path.startswith(MOUNT_PREFIX + "/") else path


def _inventory() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        if not RUN_DATA_PATH.search(path):
            continue
        if type(route).__name__ == "APIWebSocketRoute":
            found.add(("WS", _canonical(path)))
            continue
        for method in getattr(route, "methods", set()) - {"HEAD", "OPTIONS"}:
            found.add((method, _canonical(path)))
    return found


def _defined_functions(relative: str) -> set[str]:
    tree = ast.parse((REPO / relative).read_text(encoding="utf-8"), filename=relative)
    return {
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _served_key_sets() -> dict[str, frozenset[str]]:
    return {
        "_PROFILE_KEYS": public_events._PROFILE_KEYS,
        "_VERDICT_KEYS": public_events._VERDICT_KEYS,
        "_RESULT_KEYS": public_events._RESULT_KEYS,
        "_EVENT_KEYS": frozenset().union(*public_events._EVENT_KEYS.values()),
    }


def test_every_run_data_route_is_classified():
    unclassified = sorted(
        route for route in _inventory()
        if route not in DATA_ROUTES and route not in NO_DATA_ROUTES
    )
    assert unclassified == []


def test_every_classified_route_still_exists():
    stale = sorted(
        route for route in (*DATA_ROUTES, *NO_DATA_ROUTES) if route not in _inventory()
    )
    assert stale == []


@pytest.mark.parametrize("route", sorted(DATA_ROUTES))
def test_each_data_route_names_an_existing_harness_test(route):
    relative, test_name = DATA_ROUTES[route]
    assert (REPO / relative).is_file(), relative
    assert test_name in _defined_functions(relative), f"{relative}::{test_name}"


@pytest.mark.parametrize("route", sorted(NO_DATA_ROUTES))
def test_each_no_data_route_states_its_reason(route):
    assert NO_DATA_ROUTES[route].strip()


@pytest.mark.parametrize("name", sorted(_served_key_sets()))
def test_served_allowlist_holds_no_spec_4b_key(name):
    assert _served_key_sets()[name] & FORBIDDEN_4B_KEYS == frozenset()


def test_the_forbidden_list_is_not_empty_and_names_the_chunk_keys():
    assert {"chunk_id", "evidence", "version_hash", "dossier_hash"} <= FORBIDDEN_4B_KEYS
