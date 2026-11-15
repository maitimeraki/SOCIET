# tests/api/test_public_events.py
import json
import logging
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.api.public_events import _PROFILE_KEYS, project_event, project_result
from src.persona.models_persona import ProvenanceLink

_PROFILE_LINK_ID = uuid.UUID("c0ffee00-0000-4000-8000-000000000002")

FORBIDDEN = ("chunk_id", "doc_id", "version_hash", "graph_snapshot", "source_evidence",
             "summary_provenance", "llm_model", "llm_provider", "REASONING", "anchors")

AGENT_EVENT = {
    "type": "agent", "index": 1, "total": 8,
    "profile": {
        "name": "Kestra", "type": "Company", "role": "r", "stance": "POSITIVE", "strength": 0.5,
        "bio": "b", "details": "d", "confidence": 0.5, "agent_id": "a",
        "summary_provenance": [ProvenanceLink(doc_id="d1", title="Memo", breadcrumb="Sec 1",
                                              chunk_id=_PROFILE_LINK_ID).model_dump(mode="json")],
        "graph_snapshot": {"dataset_id": "ds", "version_hash": "abc"},
        "source_evidence": ["Some customer text"],
    },
}

def test_agent_event_drops_provenance_and_snapshot():
    out = json.dumps(project_event(AGENT_EVENT))
    assert not any(token in out for token in FORBIDDEN)
    assert str(_PROFILE_LINK_ID) not in out

def test_pair_turn_never_carries_a_raw_response():
    out = project_event({"type": "pair_turn", "pair_id": "ds:A:B", "response": "REASONING: secret\nANSWER: hi", "error": "boom"})
    assert "response" not in out and "REASONING" not in json.dumps(out)

def test_intent_drops_model_identity():
    out = project_event({"type": "intent", "intent": {"core_question": "q", "llm_model": "m", "llm_provider": "p", "extraction_confidence": 0.9}})
    assert out["intent"] == {"core_question": "q", "extraction_confidence": 0.9}

def test_selection_event_is_dropped():
    # The selection table is gone: no selection event reaches a client, rows or not.
    assert project_event({"type": "selection", "rows": [{"name": "A", "blended": 0.3}]}) is None

def test_unknown_event_types_are_dropped():
    assert project_event({"type": "debug_dump", "payload": "x"}) is None

def test_result_drops_selection_and_chunk_ids():
    out = project_result({"verdict": "v", "selection": [{"anchors": [1]}],
                          "provenance_by_claim": {"c": [{"doc_id": "d", "title": "T", "breadcrumb": "B", "chunk_id": "x"}]}})
    assert "selection" not in out
    assert out["provenance_by_claim"] == {"c": [{"title": "T", "breadcrumb": "B"}]}

def test_result_key_set_is_a_deliberate_allowlist():
    out = project_result({"surprise": 1, "verdict": "v"})
    assert out == {"verdict": "v"}


# --- the crossings: every one applies the same projector -----------------------

def _user(user_id):
    return SimpleNamespace(id=user_id)


@pytest.mark.asyncio
async def test_broadcast_persists_and_sends_only_the_projected_event():
    from src.api.debate_api import _DebateWSManager

    manager = _DebateWSManager(job_id=str(uuid.uuid4()))
    ws = AsyncMock()
    manager.connections.append(ws)
    with (
        patch("src.api.debate_api.run_doc.append_run_event", new=AsyncMock()) as append,
        patch("src.api.debate_api._persist_debate_run", new=AsyncMock()),
    ):
        await manager.broadcast(AGENT_EVENT)

    persisted = append.call_args.args[2]
    sent = ws.send_json.call_args.args[0]
    assert persisted == sent == project_event(AGENT_EVENT)
    assert manager.buffer == [sent]
    assert not any(token in json.dumps(sent) for token in FORBIDDEN)


@pytest.mark.asyncio
async def test_unknown_event_is_not_buffered_persisted_or_sent():
    from src.api.debate_api import _DebateWSManager

    manager = _DebateWSManager(job_id=str(uuid.uuid4()))
    ws = AsyncMock()
    manager.connections.append(ws)
    with (
        patch("src.api.debate_api.run_doc.append_run_event", new=AsyncMock()) as append,
        patch("src.api.debate_api._persist_debate_run", new=AsyncMock()) as persist,
    ):
        await manager.broadcast({"type": "debug_dump", "payload": "x"})

    assert manager.buffer == []
    assert not append.called
    assert not persist.called
    assert not ws.send_json.called


@pytest.mark.asyncio
async def test_get_debate_doc_projects_stored_events_and_result():
    from src.api.debate_api import get_debate_doc

    user_id = uuid.uuid4()
    stored = {
        "user_id": str(user_id),
        "events": [AGENT_EVENT, {"type": "debug_dump"}],
        "result": {"verdict": "v", "selection": [{"anchors": [1]}], "surprise": 1},
    }
    with (
        patch("src.api.debate_api.run_doc.read_run_doc", new=AsyncMock(return_value=stored)),
        patch("src.api.debate_api.require_owner", new=AsyncMock()),
    ):
        doc = await get_debate_doc("run", user=_user(user_id))

    assert doc["events"] == [project_event(AGENT_EVENT)]
    assert doc["result"] == {"verdict": "v"}


@pytest.mark.asyncio
async def test_get_debate_status_projects_result():
    from src.api.debate_api import get_debate_status

    user_id = uuid.uuid4()
    head = {
        "kind": "debate",
        "user_id": str(user_id),
        "status": "complete",
        "result": {"verdict": "v", "selection": [{"anchors": [1]}]},
        "error": None,
    }
    with (
        patch("src.api.debate_api.run_doc.read_run_head", new=AsyncMock(return_value=head)),
        patch("src.api.debate_api.require_owner", new=AsyncMock()),
    ):
        status = await get_debate_status("run", user=_user(user_id))

    assert status.result == {"verdict": "v"}


def test_persisted_run_result_is_projected_before_it_is_written():
    from src.api.debate_api import _job_doc

    job = {
        "job_id": "run",
        "result": {"verdict": "v", "selection": [{"anchors": [1]}], "surprise": 1},
    }

    assert _job_doc(job)["result"] == {"verdict": "v"}


@pytest.mark.asyncio
async def test_run_failure_message_hides_exception_text():
    from src.api.debate_api import _DEBATE_JOBS, _DebateWSManager, _run_debate_async
    from src.simulation.debate_config import DebateConfig

    job_id = str(uuid.uuid4())
    manager = _DebateWSManager()
    manager.broadcast = AsyncMock()
    _DEBATE_JOBS[job_id] = {"job_id": job_id, "status": "queued", "ws_manager": manager,
                            "result": None, "error": None}
    try:
        with (
            patch("src.api.debate_api._persist_debate_run", new=AsyncMock()),
            patch("src.llm.client.LLMClient", side_effect=RuntimeError("provider key sk-live-secret")),
        ):
            await _run_debate_async(job_id=job_id, query="q", graph_id="ds1",
                                    config=DebateConfig(), selected_domains=None)
        job = _DEBATE_JOBS[job_id]
    finally:
        _DEBATE_JOBS.pop(job_id, None)

    error_event = manager.broadcast.call_args.args[0]
    assert error_event["type"] == "error"
    assert "sk-live-secret" not in error_event["error"]
    assert "sk-live-secret" not in job["error"]


@pytest.mark.asyncio
async def test_not_debatable_message_reaches_the_user():
    from src.api.debate_api import _DEBATE_JOBS, _DebateWSManager, _run_debate_async
    from src.simulation.debate_config import DebateConfig
    from src.simulation.orchestrator import SocietyNotDebatableError

    job_id = str(uuid.uuid4())
    manager = _DebateWSManager()
    manager.broadcast = AsyncMock()
    _DEBATE_JOBS[job_id] = {"job_id": job_id, "status": "queued", "ws_manager": manager,
                            "result": None, "error": None}
    try:
        with (
            patch("src.api.debate_api._persist_debate_run", new=AsyncMock()),
            patch("src.llm.client.LLMClient", side_effect=SocietyNotDebatableError("Nothing to debate yet.")),
        ):
            await _run_debate_async(job_id=job_id, query="q", graph_id="ds1",
                                    config=DebateConfig(), selected_domains=None)
        job = _DEBATE_JOBS[job_id]
    finally:
        _DEBATE_JOBS.pop(job_id, None)

    assert manager.broadcast.call_args.args[0]["error"] == "Nothing to debate yet."
    assert job["error"] == "Nothing to debate yet."


# --- fix round 1 ----------------------------------------------------------------

# The link is the real model's dump, not a hand-made shape.
_REAL_LINK = ProvenanceLink(
    doc_id="DOC-XYZ", title="Memo", breadcrumb="Sec 1",
    chunk_id=uuid.UUID("c0ffee00-0000-4000-8000-000000000001"),
).model_dump(mode="json")

COMPLETE_EVENT = {
    "type": "complete", "converged": True, "verdict": "Proceed.", "narrative": "n",
    "narrative_status": "ok", "final_stances": {"Kestra": "POSITIVE"}, "warnings": [],
    "rounds_executed": 2, "confidence_score": 0.7, "weight_share": 0.7, "contested": False,
    "provenance_by_claim": {"Proceed.": [_REAL_LINK]},
    "cluster_details": {}, "supporting_entities": [], "opposing_entities": [],
    "dissenting_views": [{"stance": "NEGATIVE", "view": "view text", "quote": "Q-SECRET", "chunk_id": "X-SECRET"}],
    "evidence": [{"entity": "Acme", "claim": "claim text", "quote": "Q-SECRET", "chunk_id": "X-SECRET"}],
}
COMPLETE_LEAKS = ("DOC-XYZ", "c0ffee00-0000-4000-8000-000000000001", "Q-SECRET", "X-SECRET")
_NARROWED_EVIDENCE = [{"entity": "Acme", "claim": "claim text"}]
_NARROWED_DISSENT = [{"stance": "NEGATIVE", "view": "view text"}]


def test_complete_event_provenance_is_narrowed_like_the_result():
    assert project_event(COMPLETE_EVENT)["provenance_by_claim"] == project_result(COMPLETE_EVENT)["provenance_by_claim"]


@pytest.mark.asyncio
async def test_complete_event_leaks_no_provenance_ids_on_any_surface():
    from src.api.debate_api import _DebateWSManager, get_debate_doc

    run_id, user_id = str(uuid.uuid4()), uuid.uuid4()
    manager = _DebateWSManager(job_id=run_id)
    ws = AsyncMock()
    manager.connections.append(ws)
    with (
        patch("src.api.debate_api.run_doc.append_run_event", new=AsyncMock()) as append,
        patch("src.api.debate_api._persist_debate_run", new=AsyncMock()),
    ):
        await manager.broadcast(COMPLETE_EVENT)

    # A legacy row written before the boundary existed: the raw complete event.
    stored = {"user_id": str(user_id), "events": [COMPLETE_EVENT],
              "result": {"provenance_by_claim": COMPLETE_EVENT["provenance_by_claim"]}}
    with (
        patch("src.api.debate_api.run_doc.read_run_doc", new=AsyncMock(return_value=stored)),
        patch("src.api.debate_api.require_owner", new=AsyncMock()),
    ):
        doc = await get_debate_doc(run_id, user=_user(user_id))

    surfaces = {
        "persisted run_events row": json.dumps(append.call_args.args[2]),
        "live ws frame": json.dumps(ws.send_json.call_args.args[0]),
        "ws replay buffer": json.dumps(manager.buffer),
        "run doc (legacy row)": json.dumps(doc),
    }
    leaks = [(name, token) for name, text in surfaces.items() for token in COMPLETE_LEAKS if token in text]
    assert append.called and ws.send_json.called and manager.buffer
    assert leaks == []
    assert doc["events"][0]["provenance_by_claim"] == {"Proceed.": [{"title": "Memo", "breadcrumb": "Sec 1"}]}
    assert doc["events"][0]["evidence"] == _NARROWED_EVIDENCE
    assert doc["events"][0]["dissenting_views"] == _NARROWED_DISSENT
    assert json.loads(surfaces["live ws frame"])["evidence"] == _NARROWED_EVIDENCE
    assert json.loads(surfaces["persisted run_events row"])["dissenting_views"] == _NARROWED_DISSENT


def _export_run(verdict):
    return SimpleNamespace(
        id=uuid.uuid4(), query="q", status="complete", confidence=0.7,
        verdict=verdict,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc), finished_at=None,
    )


def test_debate_run_export_verdict_is_projected():
    from src.jobs.tasks import _run_json

    link = ProvenanceLink(doc_id="DOC-XYZ", title="T", breadcrumb="B",
                          chunk_id=uuid.UUID("c0ffee00-0000-4000-8000-000000000003")).model_dump(mode="json")
    run = _export_run({
        "verdict": "v", "selection": [{"anchors": [1]}],
        "provenance_by_claim": {"c": [link]},
        "evidence": [{"entity": "Acme", "claim": "claim text", "quote": "Q-SECRET", "chunk_id": "X-SECRET"}],
        "dissenting_views": [{"stance": "NEGATIVE", "view": "view text", "quote": "Q-SECRET"}],
    })

    out = _run_json(run, "debate")

    assert out["verdict"] == {"verdict": "v", "provenance_by_claim": {"c": [{"title": "T", "breadcrumb": "B"}]},
                              "evidence": _NARROWED_EVIDENCE, "dissenting_views": _NARROWED_DISSENT}
    text = json.dumps(out)
    assert not any(t in text for t in ("c0ffee00-0000-4000-8000-000000000003", "DOC-XYZ", "Q-SECRET", "X-SECRET"))


def test_build_graph_job_export_keeps_its_verdict_state():
    from src.jobs.tasks import _run_json

    state = {"stage": "done", "progress": 1.0, "result": {"ontology": {"classes": ["Person"]}}}

    assert _run_json(_export_run(state), "build_graph")["verdict"] == state


@pytest.mark.parametrize("kind", [["complete"], {"type": "complete"}, None, 3])
def test_non_string_event_type_is_dropped_without_logging_its_payload(kind, caplog):
    with caplog.at_level(logging.WARNING):
        assert project_event({"type": kind, "verdict": "SECRET-PAYLOAD"}) is None
    assert "SECRET-PAYLOAD" not in caplog.text


# --- fix round 3: fail closed on malformed shapes -------------------------------

def test_non_mapping_intent_is_dropped_from_the_result():
    assert project_result({"intent": "SECRET-INTENT", "verdict": "v"})["intent"] == {}


def test_non_mapping_intent_is_dropped_from_the_intent_event():
    assert project_event({"type": "intent", "intent": ["SECRET-INTENT"]}) == {"type": "intent", "intent": {}}


def test_non_mapping_provenance_is_dropped_not_passed_through():
    out = project_event({**COMPLETE_EVENT, "provenance_by_claim": [{"chunk_id": "CHUNK-XYZ"}]})
    assert out["provenance_by_claim"] == {}
    assert "CHUNK-XYZ" not in json.dumps(out)


def test_malformed_links_are_dropped_without_raising():
    out = project_result({"provenance_by_claim": {
        "c": ["CHUNK-XYZ", None, {"title": "T", "breadcrumb": "B", "chunk_id": "CHUNK-XYZ"}],
        "d": "CHUNK-XYZ",
    }})
    assert out["provenance_by_claim"] == {"c": [{"title": "T", "breadcrumb": "B"}], "d": []}


def test_non_text_title_is_dropped_not_passed_through():
    out = project_result({"provenance_by_claim": {"c": [{"title": {"chunk_id": "CHUNK-XYZ"}, "breadcrumb": "B"}]}})
    assert out["provenance_by_claim"] == {"c": [{"title": None, "breadcrumb": "B"}]}


def test_malformed_profile_does_not_raise_or_pass_through():
    agent = project_event({"type": "agent", "profile": "CHUNK-XYZ", "index": 1, "total": 2})
    assert agent["profile"] == {}


# --- fix round 4: evidence and dissenting_views are LLM output ------------------

@pytest.mark.parametrize("key", ["evidence", "dissenting_views"])
def test_llm_item_keys_are_narrowed_on_event_and_result(key):
    items = [{"entity": "A", "claim": "c", "stance": "POSITIVE", "view": "v",
              "quote": "Q-SECRET", "chunk_id": "X-SECRET", "doc_id": "D-SECRET"}]
    for out in (project_event({"type": "complete", key: items}), project_result({key: items})):
        assert "SECRET" not in json.dumps(out)


def test_evidence_and_dissent_keep_only_their_rendered_keys():
    out = project_result({
        "evidence": [{"entity": "A", "claim": "c", "quote": "Q"}],
        "dissenting_views": [{"stance": "NEGATIVE", "view": "v", "entity": "A", "quote": "Q"}],
    })
    assert out == {"evidence": [{"entity": "A", "claim": "c"}],
                   "dissenting_views": [{"stance": "NEGATIVE", "view": "v"}]}


@pytest.mark.parametrize("key", ["evidence", "dissenting_views"])
def test_malformed_llm_items_are_dropped(key):
    assert project_result({key: ["SECRET", None, 3]}) == {key: []}
    assert project_result({key: "SECRET"}) == {key: []}
    assert project_result({key: None}) == {key: []}


def test_non_text_evidence_values_are_dropped_not_passed_through():
    out = project_result({"evidence": [{"entity": {"chunk_id": "X-SECRET"}, "claim": "c"}]})
    assert "X-SECRET" not in json.dumps(out)


@pytest.mark.parametrize("event", [None, "complete", ["type"], 3])
def test_non_mapping_event_is_dropped(event):
    assert project_event(event) is None


def test_evidence_item_with_no_surviving_value_is_dropped():
    out = project_result({"evidence": [{"entity": {"chunk_id": "X-SECRET"}, "claim": 3}]})
    assert out == {"evidence": []}


def test_dissenting_view_with_no_surviving_value_is_dropped():
    out = project_event({"type": "complete", "dissenting_views": [{"stance": 1, "view": None}, {"stance": "NEG", "view": "keep"}]})
    assert out["dissenting_views"] == [{"stance": "NEG", "view": "keep"}]


def test_profile_allowlist_is_exactly_the_agent_view_keys():
    from src.simulation.agent_record import AgentView

    assert _PROFILE_KEYS == frozenset(AgentView.model_fields)


def test_roster_projection_fails_closed_on_a_raw_key():
    # The roster is the AgentView schema itself: a stored view with any key beyond it raises
    # rather than passing the key through to the client.
    from pydantic import ValidationError

    from src.api.run_doc import roster_views

    view = {"name": "Kestra", "type": "Company", "role": "r", "stance": "POSITIVE", "strength": 0.5,
            "bio": "b", "details": "d", "confidence": 0.5,
            "evidence": [{"chunk_id": "X-SECRET", "text": "Some customer text"}]}
    with pytest.raises(ValidationError):
        roster_views([view])
