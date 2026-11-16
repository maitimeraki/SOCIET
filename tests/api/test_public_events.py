# tests/api/test_public_events.py
import json
import logging
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.api.public_events import (
    _BACKEND_RESULT_KEYS,
    _PROFILE_KEYS,
    _RESULT_KEYS,
    project_event,
    project_result,
    stored_result,
)
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
    out = project_result({"converged": True, "selection": [{"anchors": [1]}],
                          "provenance_by_claim": {"c": [{"doc_id": "d", "title": "T", "breadcrumb": "B", "chunk_id": "x"}]}})
    assert "selection" not in out
    assert out["provenance_by_claim"] == {"c": [{"title": "T", "breadcrumb": "B"}]}

def test_result_key_set_is_a_deliberate_allowlist():
    assert _RESULT_KEYS == frozenset({
        "intent", "converged", "final_stances", "warnings", "rounds_executed", "confidence_score",
        "weight_share", "contested", "provenance_by_claim", "cluster_details", "supporting_entities",
        "opposing_entities", "title", "markdown", "position", "sources", "status",
    })


def test_result_drops_every_unlisted_key_and_the_backend_only_report_keys():
    out = project_result({"surprise": 1, "source_refs": {"1": {"node_id": "N"}}, "attempts": 2,
                          "checks": ["c"], "converged": True})
    assert out == {"converged": True}
    assert _BACKEND_RESULT_KEYS == frozenset({"source_refs", "attempts", "checks", "retry_inputs"})


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
        "result": {"converged": True, "selection": [{"anchors": [1]}], "surprise": 1},
    }
    with (
        patch("src.api.debate_api.run_doc.read_run_doc", new=AsyncMock(return_value=stored)),
        patch("src.api.debate_api.require_owner", new=AsyncMock()),
    ):
        doc = await get_debate_doc("run", user=_user(user_id))

    assert doc["events"] == [project_event(AGENT_EVENT)]
    assert doc["result"] == {"converged": True}


@pytest.mark.asyncio
async def test_get_debate_status_projects_result():
    from src.api.debate_api import get_debate_status

    user_id = uuid.uuid4()
    head = {
        "kind": "debate",
        "user_id": str(user_id),
        "status": "complete",
        "result": {"converged": True, "selection": [{"anchors": [1]}]},
        "error": None,
    }
    with (
        patch("src.api.debate_api.run_doc.read_run_head", new=AsyncMock(return_value=head)),
        patch("src.api.debate_api.require_owner", new=AsyncMock()),
    ):
        status = await get_debate_status("run", user=_user(user_id))

    assert status.result == {"converged": True}


def test_persisted_run_result_is_projected_before_it_is_written():
    from src.api.debate_api import _job_doc

    job = {
        "job_id": "run",
        "result": {"converged": True, "selection": [{"anchors": [1]}], "surprise": 1},
    }

    assert _job_doc(job)["result"] == {"converged": True}


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
    "type": "complete", "converged": True, "final_stances": {"Kestra": "POSITIVE"}, "warnings": [],
    "rounds_executed": 2, "confidence_score": 0.7, "weight_share": 0.7, "contested": False,
    "provenance_by_claim": {"Proceed.": [_REAL_LINK]},
    "cluster_details": {}, "supporting_entities": [], "opposing_entities": [],
    "title": "Proceed?", "markdown": "# Proceed?\n## Recommendation\nPosition: POSITIVE, 70%, settled",
    "position": "POSITIVE",
    "sources": {"1": {"document": "Memo", "section": "Sec 1", "span": "Q-SECRET", "chunk_id": "X-SECRET"}},
    "source_refs": {"1": {"node_id": "NODE-SECRET", "evidence_id": "EV-SECRET"}},
    "attempts": 3, "checks": ["SECRET-CHECK"], "status": "produced",
}
COMPLETE_LEAKS = ("DOC-XYZ", "c0ffee00-0000-4000-8000-000000000001", "Q-SECRET", "X-SECRET",
                  "NODE-SECRET", "EV-SECRET", "SECRET-CHECK")
_PUBLIC_SOURCES = {"1": {"document": "Memo", "section": "Sec 1"}}


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
    assert doc["events"][0]["sources"] == _PUBLIC_SOURCES
    assert json.loads(surfaces["live ws frame"])["sources"] == _PUBLIC_SOURCES
    assert json.loads(surfaces["persisted run_events row"])["sources"] == _PUBLIC_SOURCES
    assert "attempts" not in doc["events"][0] and "checks" not in doc["events"][0]


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
        "converged": True, "selection": [{"anchors": [1]}],
        "provenance_by_claim": {"c": [link]},
        "status": "produced", "title": "T", "markdown": "# T",
        "sources": {"1": {"document": "T", "section": "B", "span": "Q-SECRET", "chunk_id": "X-SECRET"}},
        "source_refs": {"1": {"node_id": "NODE-SECRET", "evidence_id": "EV-SECRET"}},
        "attempts": 1, "checks": ["SECRET-CHECK"],
    })

    out = _run_json(run, "debate")

    assert out["verdict"] == {"converged": True, "provenance_by_claim": {"c": [{"title": "T", "breadcrumb": "B"}]},
                              "status": "produced", "title": "T", "markdown": "# T",
                              "sources": {"1": {"document": "T", "section": "B"}}}
    text = json.dumps(out)
    assert not any(t in text for t in ("c0ffee00-0000-4000-8000-000000000003", "DOC-XYZ", "Q-SECRET", "X-SECRET",
                                       "NODE-SECRET", "EV-SECRET", "SECRET-CHECK"))


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
    assert project_result({"intent": "SECRET-INTENT", "converged": True})["intent"] == {}


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


# --- sources: the report's public source map, narrowed to {document, section} ---

def test_sources_keep_exactly_document_and_section():
    out = project_result({"sources": {"1": {"document": "Memo", "section": "Sec 1", "span": "Q-SECRET",
                                             "chunk_id": "X-SECRET", "node_id": "N-SECRET"}}})
    assert out == {"sources": {"1": {"document": "Memo", "section": "Sec 1"}}}


def test_sources_are_narrowed_on_the_complete_event_too():
    out = project_event({"type": "complete", "sources": {"1": {"document": "Memo", "section": "S",
                                                                "span": "Q-SECRET"}}})
    assert out["sources"] == {"1": {"document": "Memo", "section": "S"}}


@pytest.mark.parametrize("sources", ["SECRET", None, 3, ["SECRET"]])
def test_a_malformed_sources_map_is_empty(sources):
    assert project_result({"sources": sources}) == {"sources": {}}


def test_a_source_entry_that_is_not_a_mapping_or_not_text_is_dropped():
    out = project_result({"sources": {
        "1": "SECRET",
        "2": {"document": 7, "section": "S", "span": "Q-SECRET"},
        "3": {"document": "Memo", "section": None},
        "4": {"document": "Memo", "section": "Sec 4"},
    }})
    assert out == {"sources": {"4": {"document": "Memo", "section": "Sec 4"}}}


def test_stored_result_keeps_the_backend_only_keys_and_serves_the_public_ones():
    stored = stored_result({
        "converged": True, "status": "produced", "attempts": 2, "checks": ["attempt 1: x"],
        "source_refs": {"1": {"node_id": "N", "evidence_id": "e1"}},
        "sources": {"1": {"document": "Memo", "section": "Sec 1"}}, "surprise": 1,
    })
    assert stored == {
        "converged": True, "status": "produced", "attempts": 2, "checks": ["attempt 1: x"],
        "source_refs": {"1": {"node_id": "N", "evidence_id": "e1"}},
        "sources": {"1": {"document": "Memo", "section": "Sec 1"}},
    }


@pytest.mark.parametrize("event", [None, "complete", ["type"], 3])
def test_non_mapping_event_is_dropped(event):
    assert project_event(event) is None


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


# --- fix round 1: titles, sections and breadcrumbs are capped and stripped of control characters ---

def test_a_10k_section_is_capped_at_200_characters():
    out = project_result({"sources": {"1": {"document": "D", "section": "S" * 10_000}}})
    assert len(out["sources"]["1"]["section"]) == 200


def test_a_10k_provenance_title_is_capped_at_200_characters():
    out = project_result({"provenance_by_claim": {"c": [{"title": "T" * 10_000, "breadcrumb": "B"}]}})
    assert len(out["provenance_by_claim"]["c"][0]["title"]) == 200


def test_control_characters_are_removed_from_a_source_label():
    out = project_result({"sources": {"1": {"document": "Me\x00mo\x1b", "section": "Pri\ncing\t"}}})
    assert out == {"sources": {"1": {"document": "Memo", "section": "Pricing"}}}


# --- the retry inputs: stored for a verdict retry, never served ----------------

_RETRY_INPUTS = {
    "context": "CTX-SECRET",
    "turns": [{"agent_name": "Kestra", "round": 1, "stance": "POSITIVE",
               "cites": ["EV-CITE-SECRET"], "strength": 0.6}],
}
_RETRY_LEAKS = ("CTX-SECRET", "EV-CITE-SECRET")


def test_retry_inputs_are_stored_and_dropped_from_every_projection():
    stored_doc = {"converged": True, "status": "not_produced", "retry_inputs": _RETRY_INPUTS,
                  "attempts": 3, "checks": []}
    assert stored_result(stored_doc)["retry_inputs"] == _RETRY_INPUTS
    served = project_result(stored_doc)
    assert "retry_inputs" not in served
    complete = project_event({"type": "complete", "converged": True, "retry_inputs": _RETRY_INPUTS})
    assert "retry_inputs" not in complete
    for token in _RETRY_LEAKS:
        assert token not in json.dumps([served, complete])


@pytest.mark.asyncio
async def test_retry_inputs_leave_no_served_surface_of_a_run():
    from src.api.debate_api import get_debate_doc, get_debate_status

    run_id, user_id = str(uuid.uuid4()), uuid.uuid4()
    result = {"converged": True, "status": "not_produced", "retry_inputs": _RETRY_INPUTS,
              "attempts": 3, "checks": [], "final_stances": {}}
    stored = {"user_id": str(user_id),
              "events": [{"type": "complete", "converged": True, "retry_inputs": _RETRY_INPUTS}],
              "result": result}
    head = {"user_id": str(user_id), "kind": "debate", "status": "complete", "result": result, "error": None}
    with (
        patch("src.api.debate_api.run_doc.read_run_doc", new=AsyncMock(return_value=stored)),
        patch("src.api.debate_api.run_doc.read_run_head", new=AsyncMock(return_value=head)),
        patch("src.api.debate_api.require_owner", new=AsyncMock()),
    ):
        doc = await get_debate_doc(run_id, user=_user(user_id))
        status = await get_debate_status(run_id, user=_user(user_id))

    surfaces = {"run doc": json.dumps(doc, default=str), "status": status.model_dump_json()}
    for name, text in surfaces.items():
        for token in _RETRY_LEAKS:
            assert token not in text, (name, token)


def test_debate_export_leaves_out_the_retry_inputs():
    from src.jobs.tasks import _run_json

    run = _export_run({"converged": True, "status": "not_produced", "retry_inputs": _RETRY_INPUTS,
                       "attempts": 3, "checks": []})
    text = json.dumps(_run_json(run, "debate"), default=str)
    for token in _RETRY_LEAKS:
        assert token not in text
