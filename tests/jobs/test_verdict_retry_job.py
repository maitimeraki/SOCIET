"""The verdict retry job, run through `execute`: the rebuild from stored rows, the one report call,
the write, the hold release on every exit, and MeteringError.

Storage, billing and the LLM are faked at their module boundary; the rebuild, the board, the
bundle and the writer's checks are the real code.
"""

import contextlib
import dataclasses
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api import debate_api, run_doc
from src.api.public_events import (
    METERING_STOPPED_MESSAGE,
    REPORT_NOT_PRODUCED_MESSAGE,
    RUN_FAILED_MESSAGE,
)
from src.billing import units
from src.billing.metering import MeteringError
from src.jobs import tasks
from src.persona.agent import Agent, PersonaIdentity, Stance
from src.simulation import report_retry as rr
from src.simulation.evidence import EvidenceItem, RelationItem
from src.simulation.pair_turn import AgentTurn, RoundResult
from src.simulation.verdict import (
    NOT_PRODUCED,
    ReportResult,
    VerdictSynthesizer,
    board_facts,
    board_final_stances,
)

PASSING_MARKDOWN = "# Should we expand?\n## Recommendation\n"  # the spy returns this as a produced report


def _evidence(item_id: str, text: str) -> EvidenceItem:
    return EvidenceItem(id=item_id, chunk_id=f"chunk-{item_id}", doc_id="doc-memo", doc_title="Memo",
                        section=f"Section {item_id}", span=(0, len(text)), text=text, origin="vector",
                        retrieval_score=0.5)


def _agent(name, stance, confidence, evidence):
    return Agent(node_id=f"node-{name.lower()}", dataset_id="ds-1",
                 identity=PersonaIdentity(name=name, type_label="Company"), role="analyst", stance=stance,
                 strength=0.7, confidence=confidence, bio=f"{name} bio.", details_raw=f"{name} [e1].",
                 evidence=evidence, relations=[RelationItem(id="r1", type="supports", direction="out",
                                                            counterpart_id="x", counterpart_name="Lumen",
                                                            chunk_id="chunk-e1")],
                 cites={"stance": ["e1"]})


def _turn(agent, stance, cites, strength, content):
    return AgentTurn(agent_id=str(agent.agent_id), agent_name=agent.identity.name, content=content,
                     stance=stance, confidence=agent.confidence, strength=strength, references=["Lumen"],
                     cites=cites)


class _Store:
    """The run's rows, as the job reads them, and what the job writes back."""

    def __init__(self, rounds, profiles, stored):
        self.run_id = str(uuid.uuid4())
        self.user_id = str(uuid.uuid4())
        self.events = [
            {"type": "round", "round": r.round_num,
             "turns": [{"agent_id": t.agent_id, "agent_name": t.agent_name, "content": t.content,
                        "stance": t.stance, "confidence": t.confidence, "references": t.references}
                       for t in r.turns]}
            for r in rounds
        ]
        self.records = json.loads(json.dumps([
            {"node_id": a.node_id, "node": {"name": a.identity.name, "type_label": "Company"},
             "view": a.view().model_dump(mode="json"), "details_raw": a.details_raw,
             "evidence": [dataclasses.asdict(e) for e in a.evidence],
             "relations": [dataclasses.asdict(r) for r in a.relations], "cites": a.cites}
            for a in profiles
        ]))
        self.run = {
            "run_id": self.run_id, "kind": "debate", "user_id": self.user_id, "query": "Should we expand?",
            "status": "complete", "created_at": "2026-11-01T00:00:00+00:00", "corpus_label": None,
            "dataset_id": "ds-1", "config": {"max_rounds": 2}, "error": None,
            "result": stored, "events": self.events,
        }


def _stored(rounds, profiles, retry_inputs, *, converged=True):
    verdict = VerdictSynthesizer().synthesize(rounds=rounds, profiles=profiles)
    return {
        "converged": converged, "rounds_executed": len(rounds), "warnings": [], "intent": None,
        "final_stances": board_final_stances(rounds, profiles), "weight_share": verdict.weight_share,
        "position": board_facts(rounds, profiles, converged).position.value,
        "status": NOT_PRODUCED, "retry_inputs": retry_inputs, "attempts": 3, "checks": [],
        "source_refs": {}, "sources": {}, "title": None, "markdown": None,
    }


@pytest.fixture
def board():
    kestra = _agent("Kestra", Stance.POSITIVE, 0.8, [_evidence("e1", "Revenue grew twelve percent.")])
    orbit = _agent("Orbit", Stance.NEGATIVE, 0.5, [_evidence("e1", "Margins fell."), _evidence("e2", "Churn rose.")])
    rounds = [
        RoundResult(round_num=1, turns=[_turn(kestra, "POSITIVE", ("e1",), 0.6, "Growth supports entry."),
                                        _turn(orbit, "NEGATIVE", ("e2",), 0.4, "Churn argues against.")], pairs=[]),
        RoundResult(round_num=2, turns=[_turn(kestra, "POSITIVE", ("e1",), 0.7, "Still for entry."),
                                        _turn(orbit, "NEGATIVE", ("e1", "e2"), 0.8, "Margins and churn.")], pairs=[]),
    ]
    return rounds, [kestra, orbit]


@pytest.fixture
def store(board, monkeypatch):
    rounds, profiles = board
    retry_inputs = json.loads(json.dumps(rr.build_retry_inputs(rounds, profiles, "Should we expand?", "")))
    fake = _Store(rounds, profiles, _stored(rounds, profiles, retry_inputs))
    head = {k: v for k, v in fake.run.items() if k != "events"}

    async def read_run_doc(run_id):
        return dict(fake.run) if run_id == fake.run_id else None

    async def read_published_records(run_id):
        return list(fake.records) if run_id == fake.run_id else []

    write = AsyncMock()
    status = AsyncMock()
    released = AsyncMock(return_value=1)
    monkeypatch.setattr(run_doc, "read_run_doc", read_run_doc)
    monkeypatch.setattr(run_doc, "read_run_head", AsyncMock(return_value=head))
    monkeypatch.setattr(run_doc, "read_published_records", read_published_records)
    monkeypatch.setattr(run_doc, "write_run_doc", write)
    monkeypatch.setattr(run_doc, "set_job_status", status)
    monkeypatch.setattr(tasks, "is_cancelled", lambda job_id: False)
    monkeypatch.setattr(tasks, "_assert_reservation", AsyncMock())

    async def metering_scope(kind, job_id, payload):
        return contextlib.nullcontext()

    monkeypatch.setattr(tasks, "_metering_scope", metering_scope)
    monkeypatch.setattr(units, "release_job_reservation", released)
    monkeypatch.setattr("src.audit.record", AsyncMock())
    monkeypatch.setattr("src.llm.client.LLMClient", lambda *a, **k: SimpleNamespace(generate=None))

    session = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(user_id=uuid.UUID(fake.user_id))))

    @contextlib.asynccontextmanager
    async def session_scope():
        yield session

    monkeypatch.setattr("src.db.engine.get_session_factory", lambda: lambda: session_scope())
    fake.write, fake.status, fake.released = write, status, released
    fake.job_id = str(uuid.uuid4())
    fake.payload = {"user_id": fake.user_id, "run_id": fake.run_id, "reserved_units": 3,
                    "reserved_period_start": "2026-11-01T00:00:00+00:00", "reserved_at": "2026-11-16T00:00:00+00:00"}
    return fake


def _spy_write_report(monkeypatch, outcome):
    """Replace the report writer with a spy: `outcome` is a ReportResult, None, or an exception."""
    calls = []

    async def write_report(client, bundle, facts, source_ids):
        calls.append((bundle, facts))
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr("src.simulation.verdict.write_report", write_report)
    return calls


PRODUCED = ReportResult(markdown=PASSING_MARKDOWN, attempts=1, checks=[])


@pytest.mark.asyncio
async def test_the_job_writes_the_report_once_from_the_stored_rows(store, monkeypatch):
    calls = _spy_write_report(monkeypatch, PRODUCED)

    await tasks.execute("verdict", store.job_id, store.payload)

    assert len(calls) == 1
    bundle, facts = calls[0]
    assert bundle.question == "Should we expand?"
    assert [citizen.name for citizen in bundle.citizens] == ["Kestra", "Orbit"]
    store.write.assert_awaited_once()
    written = store.write.await_args.args[0]
    assert written["run_id"] == store.run_id and written["status"] == "complete"
    assert written["result"]["status"] == "produced"
    assert written["result"]["retry_inputs"] == store.run["result"]["retry_inputs"]


@pytest.mark.asyncio
async def test_the_job_releases_the_unused_hold_on_success(store, monkeypatch):
    _spy_write_report(monkeypatch, PRODUCED)

    await tasks.execute("verdict", store.job_id, store.payload)

    store.released.assert_awaited_once()
    assert store.status.await_args_list[-1].args[1] == "completed"


@pytest.mark.asyncio
async def test_a_report_that_still_fails_leaves_the_run_not_produced_and_releases_the_hold(store, monkeypatch):
    calls = _spy_write_report(monkeypatch, None)

    await tasks.execute("verdict", store.job_id, store.payload)

    assert len(calls) == 1
    store.write.assert_not_awaited()
    store.released.assert_awaited_once()
    outcomes = [call for call in store.status.await_args_list if call.args[1] == "failed"]
    assert [call.kwargs["error"] for call in outcomes] == [REPORT_NOT_PRODUCED_MESSAGE]


@pytest.mark.asyncio
async def test_a_metering_error_stops_the_job_and_is_re_raised_without_a_fallback(store, monkeypatch):
    _spy_write_report(monkeypatch, MeteringError("balance exhausted"))

    with pytest.raises(MeteringError):
        await tasks.execute("verdict", store.job_id, store.payload)

    store.write.assert_not_awaited()
    store.released.assert_awaited_once()
    assert store.status.await_args_list[-1].kwargs["error"] == METERING_STOPPED_MESSAGE


@pytest.mark.asyncio
async def test_a_rebuild_that_does_not_match_the_stored_board_writes_nothing_and_calls_no_model(store, monkeypatch):
    calls = _spy_write_report(monkeypatch, PRODUCED)
    store.run["result"] = {**store.run["result"], "final_stances": {"Kestra": "NEGATIVE", "Orbit": "NEGATIVE"}}

    with pytest.raises(rr.RetryDataError):
        await tasks.execute("verdict", store.job_id, store.payload)

    assert calls == []
    store.write.assert_not_awaited()
    store.released.assert_awaited_once()
    failure = store.status.await_args_list[-1]
    assert failure.args[1] == "failed" and failure.kwargs["error"] == RUN_FAILED_MESSAGE


@pytest.mark.asyncio
async def test_a_run_without_retry_inputs_fails_the_job_before_any_call(store, monkeypatch):
    calls = _spy_write_report(monkeypatch, PRODUCED)
    store.run["result"] = {k: v for k, v in store.run["result"].items() if k != "retry_inputs"}

    with pytest.raises(rr.RetryDataError):
        await tasks.execute("verdict", store.job_id, store.payload)

    assert calls == []
    store.write.assert_not_awaited()
    store.released.assert_awaited_once()


def test_the_verdict_kind_is_registered_as_a_metered_job():
    assert "verdict" in tasks.TASKS and "verdict" in tasks.CORES
    assert tasks._METERED_SOURCES["verdict"] == "verdict"
    assert tasks._SUCCESS_STATUS["verdict"] == "completed"


def test_the_verdict_estimate_is_three_report_calls():
    assert debate_api.verdict_retry_reserve_units() == 3 * debate_api.report_call_units()


@pytest.mark.asyncio
async def test_a_board_fingerprint_that_differs_from_the_debate_is_refused_before_any_call(store, monkeypatch):
    calls = _spy_write_report(monkeypatch, PRODUCED)
    store.run["result"]["retry_inputs"]["board"]["sources"] = ["1"]

    with pytest.raises(rr.RetryDataError):
        await tasks.execute("verdict", store.job_id, store.payload)

    assert calls == []
    store.write.assert_not_awaited()
    store.released.assert_awaited_once()
