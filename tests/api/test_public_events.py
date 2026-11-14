# tests/api/test_public_events.py
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.api.public_events import project_event, project_result

FORBIDDEN = ("chunk_id", "doc_id", "version_hash", "graph_snapshot", "source_evidence",
             "summary_provenance", "llm_model", "llm_provider", "REASONING", "anchors")

AGENT_EVENT = {
    "type": "agent", "index": 1, "total": 8,
    "profile": {
        "agent_id": "a", "identity": {"name": "Kestra", "archetype": "x", "communication_style": "y"},
        "bio": "b", "detailed_perspective": "d", "stance": "POSITIVE", "intensity": 0.5, "confidence": 0.5,
        "summary_provenance": [{"doc_id": "d1", "title": "Memo", "chunk_id": "c1"}],
        "graph_snapshot": {"dataset_id": "ds", "version_hash": "abc"},
        "source_evidence": ["Some customer text"],
    },
}

def test_agent_event_drops_provenance_and_snapshot():
    out = json.dumps(project_event(AGENT_EVENT))
    assert not any(token in out for token in FORBIDDEN)

def test_pair_turn_never_carries_a_raw_response():
    out = project_event({"type": "pair_turn", "pair_id": "ds:A:B", "response": "REASONING: secret\nANSWER: hi", "error": "boom"})
    assert "response" not in out and "REASONING" not in json.dumps(out)

def test_intent_drops_model_identity():
    out = project_event({"type": "intent", "intent": {"core_question": "q", "llm_model": "m", "llm_provider": "p", "extraction_confidence": 0.9}})
    assert out["intent"] == {"core_question": "q", "extraction_confidence": 0.9}

def test_selection_rows_lose_anchors():
    out = project_event({"type": "selection", "rows": [{"name": "A", "semantic": 0.1, "density": 0.2, "blended": 0.3,
                                                         "anchors": [{"kind": "chunk", "id": "c1"}]}]})
    assert "anchors" not in out["rows"][0]

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
