"""The verdict retry gate, without a database.

The route runs for real: CSRF, ownership, the refusals, the reserve, the enqueue and the audit.
Only the storage and billing calls at the module boundary are faked (run head, in-flight check,
entitlements, reserve, release, enqueue, audit), so each guard's order and its no-reserve
property is observable here.
"""

import datetime
import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import src.api.debate_api as debate_api
from src.api import run_doc
from src.api.debate_api import router as debate_router
from src.api.errors import install_error_handlers
from src.auth.cookies import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from src.auth.deps import current_user
from src.billing import units as billing_units
from src.config.settings import get_settings
from src.db.engine import get_db
from src.llm.config_llm import get_llm_config
from src.simulation.report_retry import (
    REFUSAL_IN_FLIGHT,
    REFUSAL_NOT_PENDING,
    REFUSAL_NOT_RETRYABLE,
)
from src.simulation.verdict import REPORT_MAX_ATTEMPTS

RETRY_INPUTS = {"context": "", "turns": []}
NOT_PRODUCED = {"status": "not_produced", "retry_inputs": RETRY_INPUTS, "converged": True,
                "final_stances": {}, "attempts": 3, "checks": [], "position": None}


class World:
    """The fake store: runs, the in-flight set, the balance, and every billing and queue call."""

    def __init__(self, user_id):
        self.user_id = user_id
        self.runs: dict[str, dict] = {}
        self.in_flight: set[str] = set()
        self.remaining = 10_000
        self.reserves: list[int] = []
        self.releases: list[int] = []
        self.enqueued: list[tuple[str, dict]] = []
        self.audits: list[str] = []
        self.audit_meta: list[dict] = []
        self.enqueue_error: Exception | None = None


def _head(world: World, run_id: str, *, result, owner=None, kind="debate") -> dict:
    return {
        "run_id": run_id, "user_id": str(owner or world.user_id), "kind": kind,
        "created_at": "2026-11-01T00:00:00+00:00", "query": "Should we expand?",
        "corpus_label": None, "status": "complete", "result": result, "error": None,
    }


@pytest.fixture
def world(monkeypatch):
    user_id = uuid.uuid4()
    state = World(user_id)

    async def read_run_head(run_id):
        head = state.runs.get(run_id)
        return dict(head) if head is not None else None

    async def verdict_job_in_flight(run_id):
        return run_id in state.in_flight

    async def resolve_entitlements(db, *, user):
        return SimpleNamespace(units_remaining=state.remaining)

    async def reserve_units(db, *, user_id, plan_key, estimate, now=None):
        if estimate > state.remaining:
            raise billing_units.InsufficientUnits(datetime.datetime(2026, 12, 1, tzinfo=datetime.timezone.utc))
        state.reserves.append(estimate)
        start = datetime.datetime(2026, 11, 1, tzinfo=datetime.timezone.utc)
        return billing_units.Reservation(
            user_id=user_id, period_start=start, period_end=start + datetime.timedelta(days=30),
            amount=estimate, units_used=0, units_reserved=estimate,
        )

    async def release_reservation(db, *, user_id, period_start, amount):
        state.releases.append(amount)

    async def enqueue_or_http(kind, payload):
        if state.enqueue_error is not None:
            raise state.enqueue_error
        job_id = str(uuid.uuid4())
        state.enqueued.append((kind, payload))
        state.in_flight.add(payload["run_id"])
        return job_id

    async def audit_record(db, action, **kwargs):
        state.audits.append(action)
        state.audit_meta.append(kwargs.get("meta") or {})

    monkeypatch.setattr(run_doc, "read_run_head", read_run_head)
    monkeypatch.setattr(run_doc, "verdict_job_in_flight", verdict_job_in_flight)
    monkeypatch.setattr(debate_api, "resolve_entitlements", resolve_entitlements)
    monkeypatch.setattr(billing_units, "reserve_units", reserve_units)
    monkeypatch.setattr(billing_units, "release_reservation", release_reservation)
    monkeypatch.setattr(debate_api, "enqueue_or_http", enqueue_or_http)
    monkeypatch.setattr(debate_api, "audit_record", audit_record)
    return state


@pytest.fixture
def user(world):
    return SimpleNamespace(id=world.user_id, plan_key="free")


def _client(world, user, ip):
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(debate_router)
    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: object()
    transport = ASGITransport(app=app, client=(ip, 5000), raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://testserver")


def _ip() -> str:
    return f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"


async def _retry(world, user, run_id, **kwargs):
    async with _client(world, user, _ip()) as http:
        return await http.post(f"/simulate/debates/{run_id}/verdict/retry", **kwargs)


def _refusal_code(response) -> str:
    return response.json()["error"]["code"]


@pytest.mark.asyncio
async def test_csrf_is_required_for_a_session_request(world, user):
    run_id = str(uuid.uuid4())
    world.runs[run_id] = _head(world, run_id, result=NOT_PRODUCED)

    async with _client(world, user, _ip()) as http:
        response = await http.post(
            f"/simulate/debates/{run_id}/verdict/retry", cookies={SESSION_COOKIE: "session-token"}
        )

    assert response.status_code == 403
    assert world.enqueued == [] and world.reserves == []


@pytest.mark.asyncio
async def test_a_matching_csrf_token_is_accepted(world, user):
    run_id = str(uuid.uuid4())
    world.runs[run_id] = _head(world, run_id, result=NOT_PRODUCED)

    async with _client(world, user, _ip()) as http:
        response = await http.post(
            f"/simulate/debates/{run_id}/verdict/retry",
            cookies={SESSION_COOKIE: "session-token", CSRF_COOKIE: "t0k"},
            headers={CSRF_HEADER: "t0k"},
        )

    assert response.status_code == 202


@pytest.mark.asyncio
async def test_an_unknown_run_is_the_flat_not_found(world, user):
    response = await _retry(world, user, str(uuid.uuid4()))

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Not found."


@pytest.mark.asyncio
async def test_a_foreign_run_is_the_same_flat_not_found(world, user):
    run_id = str(uuid.uuid4())
    world.runs[run_id] = _head(world, run_id, result=NOT_PRODUCED, owner=uuid.uuid4())

    response = await _retry(world, user, run_id)

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Not found."
    assert world.reserves == [] and world.enqueued == []


@pytest.mark.asyncio
async def test_a_run_that_is_not_a_debate_is_the_flat_not_found(world, user):
    run_id = str(uuid.uuid4())
    world.runs[run_id] = _head(world, run_id, result=NOT_PRODUCED, kind="ontology")

    response = await _retry(world, user, run_id)

    assert response.status_code == 404
    assert world.reserves == []


@pytest.mark.asyncio
async def test_a_produced_report_is_not_retried(world, user):
    run_id = str(uuid.uuid4())
    world.runs[run_id] = _head(world, run_id, result={**NOT_PRODUCED, "status": "produced"})

    response = await _retry(world, user, run_id)

    assert response.status_code == 409
    assert _refusal_code(response) == REFUSAL_NOT_PENDING
    assert world.reserves == [] and world.enqueued == []


@pytest.mark.asyncio
async def test_a_running_run_with_no_verdict_is_not_retried(world, user):
    run_id = str(uuid.uuid4())
    world.runs[run_id] = _head(world, run_id, result=None)

    response = await _retry(world, user, run_id)

    assert response.status_code == 409
    assert _refusal_code(response) == REFUSAL_NOT_PENDING
    assert world.reserves == []


@pytest.mark.asyncio
async def test_an_old_run_without_retry_inputs_is_not_retryable(world, user):
    run_id = str(uuid.uuid4())
    result = {key: value for key, value in NOT_PRODUCED.items() if key != "retry_inputs"}
    world.runs[run_id] = _head(world, run_id, result=result)

    response = await _retry(world, user, run_id)

    assert response.status_code == 409
    assert _refusal_code(response) == REFUSAL_NOT_RETRYABLE
    assert world.reserves == [] and world.enqueued == []


@pytest.mark.asyncio
async def test_a_retry_already_in_flight_is_refused_before_any_reserve(world, user):
    run_id = str(uuid.uuid4())
    world.runs[run_id] = _head(world, run_id, result=NOT_PRODUCED)
    world.in_flight.add(run_id)

    response = await _retry(world, user, run_id)

    assert response.status_code == 409
    assert _refusal_code(response) == REFUSAL_IN_FLIGHT
    assert world.reserves == [] and world.enqueued == []


@pytest.mark.asyncio
async def test_a_retry_reserves_the_reserve_and_enqueues_one_verdict_job(world, user):
    run_id = str(uuid.uuid4())
    world.runs[run_id] = _head(world, run_id, result=NOT_PRODUCED)

    response = await _retry(world, user, run_id)

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["run_id"] == run_id
    assert world.reserves == [debate_api.verdict_retry_reserve_units()]
    [(kind, payload)] = world.enqueued
    assert kind == "verdict"
    assert payload["run_id"] == run_id and payload["user_id"] == str(world.user_id)
    assert world.audits == ["units_reserve", "verdict_retry"]


@pytest.fixture
def reserve_setting(monkeypatch):
    """Set or clear VERDICT_RETRY_RESERVE_UNITS for one test; the settings cache is reset either way."""
    def set_value(value):
        if value is None:
            monkeypatch.delenv("VERDICT_RETRY_RESERVE_UNITS", raising=False)
        else:
            monkeypatch.setenv("VERDICT_RETRY_RESERVE_UNITS", str(value))
        get_settings.cache_clear()
    yield set_value
    get_settings.cache_clear()


def test_the_reserve_is_three_report_calls_by_default(reserve_setting):
    reserve_setting(None)

    assert debate_api.verdict_retry_reserve_units() == REPORT_MAX_ATTEMPTS * debate_api.report_call_units()


def test_the_report_call_is_sized_from_the_report_prompt_and_its_completion_cap(reserve_setting):
    from math import ceil

    from src.billing.units import units_for_tokens
    from src.llm.config_llm import get_llm_config

    reserve_setting(None)

    expected = units_for_tokens(ceil(debate_api.report_prompt_chars() / 4), get_llm_config().verdict_max_tokens)
    assert debate_api.report_call_units() == expected


def test_the_hold_follows_the_report_completion_cap_not_the_profile_cap(reserve_setting, monkeypatch):
    reserve_setting(None)
    base = debate_api.verdict_retry_reserve_units()

    try:
        monkeypatch.setenv("PROFILE_MAX_TOKENS", "9000")
        get_llm_config.cache_clear()
        assert debate_api.verdict_retry_reserve_units() == base

        monkeypatch.setenv("VERDICT_MAX_TOKENS", "6000")
        get_llm_config.cache_clear()
        assert debate_api.verdict_retry_reserve_units() > base
    finally:
        monkeypatch.undo()
        get_llm_config.cache_clear()


def test_a_configured_reserve_overrides_the_derived_one(reserve_setting):
    reserve_setting(7)

    assert debate_api.verdict_retry_reserve_units() == 7


def test_the_estimate_is_capped_at_the_remaining_units_and_floored_at_one():
    reserve = debate_api.verdict_retry_reserve_units()

    assert debate_api.verdict_retry_estimate(10**9) == reserve
    assert debate_api.verdict_retry_estimate(5) == min(reserve, 5)
    assert debate_api.verdict_retry_estimate(0) == 1


@pytest.mark.asyncio
async def test_the_reserve_is_capped_at_the_remaining_units(world, user):
    run_id = str(uuid.uuid4())
    world.runs[run_id] = _head(world, run_id, result=NOT_PRODUCED)
    world.remaining = 5

    response = await _retry(world, user, run_id)

    assert response.status_code == 202
    assert world.reserves == [5]


@pytest.mark.asyncio
async def test_no_units_left_is_the_existing_payment_required_response(world, user):
    run_id = str(uuid.uuid4())
    world.runs[run_id] = _head(world, run_id, result=NOT_PRODUCED)
    world.remaining = 0

    response = await _retry(world, user, run_id)

    assert response.status_code == 402
    assert response.json()["error"]["code"] == "payment_required"
    assert world.enqueued == []
    assert world.audits == ["units_denied"]


@pytest.mark.asyncio
async def test_a_double_submit_enqueues_one_job_and_reserves_once(world, user):
    run_id = str(uuid.uuid4())
    world.runs[run_id] = _head(world, run_id, result=NOT_PRODUCED)

    async with _client(world, user, _ip()) as http:
        first = await http.post(f"/simulate/debates/{run_id}/verdict/retry")
        second = await http.post(f"/simulate/debates/{run_id}/verdict/retry")

    assert first.status_code == 202
    assert second.status_code == 409
    assert _refusal_code(second) == REFUSAL_IN_FLIGHT
    assert len(world.enqueued) == 1
    assert len(world.reserves) == 1


@pytest.mark.asyncio
async def test_a_racing_second_insert_is_refused_and_its_hold_released(world, user):
    run_id = str(uuid.uuid4())
    world.runs[run_id] = _head(world, run_id, result=NOT_PRODUCED)
    world.enqueue_error = run_doc.VerdictJobInFlight(run_id)

    response = await _retry(world, user, run_id)

    assert response.status_code == 409
    assert _refusal_code(response) == REFUSAL_IN_FLIGHT
    assert world.reserves == world.releases != []
    assert world.enqueued == []
    assert world.audit_meta[-1]["reason"] == "verdict_job_in_flight"


@pytest.mark.asyncio
async def test_an_enqueue_failure_releases_the_hold_and_surfaces_no_detail(world, user):
    run_id = str(uuid.uuid4())
    world.runs[run_id] = _head(world, run_id, result=NOT_PRODUCED)
    world.enqueue_error = RuntimeError("redis is down: secret-host:6379")

    response = await _retry(world, user, run_id)

    assert response.status_code == 500
    assert "secret-host" not in response.text
    assert world.releases == world.reserves != []


@pytest.mark.asyncio
async def test_the_retry_rate_limit_is_enforced(world, user, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_VERDICT_RETRY", "1/hour")
    get_settings.cache_clear()
    try:
        run_id = str(uuid.uuid4())
        world.runs[run_id] = _head(world, run_id, result=NOT_PRODUCED)
        ip = _ip()
        async with _client(world, user, ip) as http:
            first = await http.post(f"/simulate/debates/{run_id}/verdict/retry")
            second = await http.post(f"/simulate/debates/{run_id}/verdict/retry")
    finally:
        monkeypatch.delenv("RATE_LIMIT_VERDICT_RETRY", raising=False)
        get_settings.cache_clear()

    assert first.status_code == 202
    assert second.status_code == 429
    assert len(world.enqueued) == 1


@pytest.mark.asyncio
async def test_nothing_from_the_request_body_is_used(world, user):
    run_id = str(uuid.uuid4())
    world.runs[run_id] = _head(world, run_id, result=NOT_PRODUCED)

    response = await _retry(world, user, run_id, json={"run_id": str(uuid.uuid4()), "units": 99999})

    assert response.status_code == 202
    [(_, payload)] = world.enqueued
    assert payload["run_id"] == run_id
    assert world.reserves == [debate_api.verdict_retry_reserve_units()]


def test_the_debate_result_stores_the_retry_inputs_and_serves_none_of_them():
    from src.api.public_events import project_event, project_result, stored_result
    from src.simulation.orchestrator import OrchestratedDebateResult

    retry_inputs = {"context": "CTX-SECRET", "turns": [{"agent_name": "K", "round": 1, "stance": "POSITIVE",
                                                       "cites": ["EV-CITE-SECRET"], "strength": 0.5}]}
    result = OrchestratedDebateResult(
        converged=True, final_stances={"K": "POSITIVE"}, warnings=[], rounds_executed=1,
        report={"status": "produced", "title": "Q?", "markdown": "# Q?", "position": "POSITIVE",
                "sources": {}, "source_refs": {}, "attempts": 1, "checks": []},
        retry_inputs=retry_inputs,
    )
    stored = debate_api._job_result(result, intent=None, retry_inputs=result.retry_inputs)
    complete = {"type": "complete", **debate_api._verdict_payload(result)}

    assert stored_result(stored)["retry_inputs"] == retry_inputs
    served = [project_result(stored), project_event(complete)]
    assert "retry_inputs" not in json.dumps(served)
    assert "CTX-SECRET" not in json.dumps(served) and "EV-CITE-SECRET" not in json.dumps(served)


def test_a_result_over_the_turn_log_bound_stores_no_retry_inputs():
    from src.simulation.orchestrator import OrchestratedDebateResult

    result = OrchestratedDebateResult(converged=False, final_stances={}, warnings=[], rounds_executed=0)

    assert "retry_inputs" not in debate_api._job_result(result, intent=None, retry_inputs=result.retry_inputs)
