"""Tests for DebateOrchestrator."""

import copy
import dataclasses
import json
import re
import uuid
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from src.api.public_events import project_event, project_result
from src.api.run_doc import roster_views
from src.billing.metering import MeteringError
from src.persona.agent import Agent, Stance
from src.persona.graph_context import EntityNode
from src.persona.models_persona import ProvenanceLink
from src.simulation.agent_record import AgentView
from src.simulation.debate_config import DebateConfig
from src.simulation.llm_batch import BatchedLLMRunner, PairResult
from src.simulation.orchestrator import (
    DebateOrchestrator,
    OrchestratedDebateResult,
    SocietyNotDebatableError,
)
from src.simulation.pair_turn import (
    ActivationCandidate,
    AgentTurn,
    CommPair,
    DebateVerdict,
    RoundResult,
)
from src.simulation.profile_synthesizer import ProfileSynthesizer
from src.simulation.society_memory import SocietyMemory, SocietySnapshot
from src.simulation.topology import CommunicationTopology
from src.simulation.verdict import VerdictSynthesizer
from src.utils.queryIntend import QueryIntent
from tests.agent_factory import slim_agent
from tests.simulation.test_profile_synthesizer import (
    FakeGraph,
    FakeLLM,
    _chunks_for,
    _repo,
)


def _make_profile(agent_id: int, name: str) -> Agent:
    """Canonical Agent stand-in — the debate loop reads it, so every field must resolve."""
    return slim_agent(
        name,
        agent_id=uuid.UUID(int=agent_id),
        bio=f"{name} perspective",
        details_raw=f"{name} perspective",
        role=f"{name}_domain",
        confidence=0.7,
    )


def _ok_receipt() -> dict:
    """The receipt shape `SocietyMemory.commit_round` returns on success."""
    return {
        "round": 1,
        "dataset_id": "ds1",
        "query_hash": "qhash",
        "opinions": 2,
        "edges": 1,
        "failed": False,
    }


def _make_verdict(summary: str = "Test verdict.") -> DebateVerdict:
    return DebateVerdict(
        overall_stance=Stance.POSITIVE,
        confidence_score=0.9,
        supporting_entities=[],
        opposing_entities=[],
        summary=summary,
        cluster_details={},
        rounds_executed=1,
    )


def _make_turn(
    agent_id: str, agent_name: str, stance: str = "POSITIVE", strength: float = 0.5
) -> AgentTurn:
    return AgentTurn(
        agent_id=agent_id,
        agent_name=agent_name,
        content="Test content",
        stance=stance,
        confidence=0.8,
        references=[],
        strength=strength,
    )


class _AsyncEmptyIter:
    """An async iterator that yields nothing."""

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


@pytest.mark.asyncio
async def test_five_step_flow():
    """Verify all 5 steps execute: profiles → topology → round → verdict → graph commit."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)

    profiles = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    synth.synthesize.return_value = profiles
    topo.compute_round_pairs.return_value = [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    verdict_synth.asynthesize.return_value = _make_verdict()
    llm_runner.gather = MagicMock(return_value=_AsyncEmptyIter())
    # Explicit successful receipt: an unset AsyncMock return degrades to the commit-failed branch.
    society_memory.commit_round.return_value = _ok_receipt()

    orchestrator = DebateOrchestrator(
        profile_synthesizer=synth,
        topology=topo,
        llm_runner=llm_runner,
        verdict_synthesizer=verdict_synth,
        society_memory=society_memory,
    )

    ws_broadcast = AsyncMock()
    config = DebateConfig(max_agents=5, max_rounds=3)

    result = await orchestrator.run("test query", "ds1", config, ws_broadcast)

    # Step 1: profile_synthesizer called — with the run's config, its warnings
    # sink, the caller-owned seat decisions sink and the run's LLM client
    synth.synthesize.assert_awaited_once_with(
        query="test query",
        dataset_id="ds1",
        max_agents=5,
        intent=None,
        warnings=result.warnings,
        decisions=ANY,
        records=ANY,
        llm_client=None,
        on_profile=ANY,
        llm_concurrency=8,
    )

    # Step 2: topology called per round (max_rounds=3)
    assert topo.compute_round_pairs.call_count == 3

    # Step 3: verdict synthesized once
    verdict_synth.asynthesize.assert_called_once()

    # Step 4: every round committed to the graph; snapshot read from round 2 on
    assert society_memory.commit_round.call_count == result.rounds_executed
    if result.rounds_executed > 1:
        assert society_memory.read_snapshot.call_count == result.rounds_executed - 1
    else:
        society_memory.read_snapshot.assert_not_awaited()

    assert isinstance(result, OrchestratedDebateResult)
    assert result.verdict == "Test verdict."
    assert result.rounds_executed == 3

    # F41.1: the commit receipt must be broadcast, not silently degraded
    sent = [c.args[0] for c in ws_broadcast.call_args_list if c.args]
    assert any(m.get("type") == "commit" for m in sent)
    assert not any("commit failed" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_ws_broadcast_passed_to_round_runner():
    """ws_broadcast is passed through to RoundRunner constructor."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)

    profiles = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    synth.synthesize.return_value = profiles
    topo.compute_round_pairs.return_value = [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    verdict_synth.asynthesize.return_value = _make_verdict()
    llm_runner.gather = MagicMock(return_value=_AsyncEmptyIter())
    # Explicit successful receipt: an unset AsyncMock return degrades to the commit-failed branch.
    society_memory.commit_round.return_value = _ok_receipt()

    orchestrator = DebateOrchestrator(
        profile_synthesizer=synth,
        topology=topo,
        llm_runner=llm_runner,
        verdict_synthesizer=verdict_synth,
        society_memory=society_memory,
    )

    ws_calls = []

    async def fake_ws(msg):
        ws_calls.append(msg)

    config = DebateConfig(max_agents=5, max_rounds=1)

    # Patch RoundRunner so we can assert ws_broadcast is captured
    with patch("src.simulation.orchestrator.RoundRunner") as patched_rr_class:
        patched_rr_instance = MagicMock()
        patched_rr_instance.execute_round = AsyncMock(
            return_value=RoundResult(round_num=1, turns=[], pairs=[])
        )
        patched_rr_class.return_value = patched_rr_instance

        result = await orchestrator.run("test query", "ds1", config, fake_ws)

        # Verify RoundRunner was constructed with the ws_broadcast
        patched_rr_class.assert_called_once()
        call_kwargs = patched_rr_class.call_args.kwargs
        assert "ws_broadcast" in call_kwargs
        assert call_kwargs["ws_broadcast"] is fake_ws

        # F41.1: the commit receipt must be broadcast, not silently degraded
        assert any(m.get("type") == "commit" for m in ws_calls)
        assert not any("commit failed" in w for w in result.warnings)
        # ...and its payload must carry the keys the WS client reads
        commit_msg = next(m for m in ws_calls if m.get("type") == "commit")
        assert commit_msg["round"] == 1
        assert set(commit_msg) >= set(_ok_receipt())


@pytest.mark.asyncio
async def test_non_debatable_roster_raises():
    """0 or 1 agents cannot debate: the job fails loudly, nothing else runs."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)
    orch = _orch(synth, topo, society_memory, verdict_synth)

    for roster in ([], [_make_profile(1, "Alice")]):
        synth.synthesize.return_value = roster
        with pytest.raises(SocietyNotDebatableError, match="at least 2"):
            await orch.run(
                "q", "ds1", DebateConfig(max_agents=5, max_rounds=3), AsyncMock()
            )

    topo.compute_round_pairs.assert_not_awaited()
    verdict_synth.asynthesize.assert_not_called()
    society_memory.commit_round.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_debatable_raises_after_the_synthesis_stage_event():
    """The stream shows how far the run got; the error is what ends it."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)
    synth.synthesize.return_value = [_make_profile(1, "Alice")]
    orch = _orch(synth, topo, society_memory)
    events, emit = _stage_spy()

    with pytest.raises(SocietyNotDebatableError):
        await orch.run(
            "q",
            "ds1",
            DebateConfig(max_agents=5, max_rounds=1),
            AsyncMock(),
            on_stage=emit,
        )

    assert [(e["stage"], e.get("agents")) for e in events] == [
        ("intake", None),
        ("selection", None),
        ("synthesis", 1),
    ]


@pytest.mark.asyncio
async def test_convergence_check_breaks_loop():
    """Loop breaks early when _check_convergence returns True."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)

    profiles = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    synth.synthesize.return_value = profiles
    topo.compute_round_pairs.return_value = [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    # Always return pairs so no round hits `continue`
    topo.compute_round_pairs.side_effect = lambda *a, **kw: [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    verdict_synth.asynthesize.return_value = _make_verdict()
    # Fresh iterator per call so each round gets an empty async iterator
    llm_runner.gather = MagicMock(side_effect=lambda *a, **kw: _AsyncEmptyIter())
    # Explicit successful receipt: an unset AsyncMock return degrades to the commit-failed branch.
    society_memory.commit_round.return_value = _ok_receipt()

    orchestrator = DebateOrchestrator(
        profile_synthesizer=synth,
        topology=topo,
        llm_runner=llm_runner,
        verdict_synthesizer=verdict_synth,
        society_memory=society_memory,
    )

    # Override _check_convergence with a sync function (same signature as the real method)
    def fake_convergence(rounds, profiles=None, config=None):
        return len(rounds) >= 2

    orchestrator._check_convergence = fake_convergence

    ws_broadcast = AsyncMock()
    config = DebateConfig(max_agents=5, max_rounds=5)

    result = await orchestrator.run("test query", "ds1", config, ws_broadcast)

    # Should stop at 2 rounds instead of max_rounds=5
    assert topo.compute_round_pairs.call_count == 2

    # F41.1: the commit receipt must be broadcast, not silently degraded
    sent = [c.args[0] for c in ws_broadcast.call_args_list if c.args]
    assert any(m.get("type") == "commit" for m in sent)
    assert not any("commit failed" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_non_debatable_raise_carries_the_accumulated_warnings():
    """A failed run must not lose its diagnostics: the warnings ride the exception."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)

    async def synthesize(**kwargs):
        kwargs["warnings"].append("actor filter degraded")
        return [_make_profile(1, "Alice")]

    synth.synthesize.side_effect = synthesize
    orch = _orch(synth, topo, society_memory)

    with pytest.raises(SocietyNotDebatableError, match="at least 2") as excinfo:
        await orch.run(
            "q", "ds1", DebateConfig(max_agents=5, max_rounds=1), AsyncMock()
        )

    assert excinfo.value.warnings == ["actor filter degraded"]


@pytest.mark.asyncio
async def test_failed_round_raises_cause_aware_message_with_warnings():
    """Rounds that raise are 'rounds raised', not 'no pair shared context' — and the
    accumulated failure diagnostics survive on the exception."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)
    synth.synthesize.return_value = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    topo.compute_round_pairs.side_effect = RuntimeError("cypher down")
    orch = _orch(synth, topo, society_memory)
    config = DebateConfig(max_agents=5, max_rounds=2, max_new_agents_per_round=0)

    with pytest.raises(SocietyNotDebatableError) as excinfo:
        await orch.run("q", "ds1", config, AsyncMock())

    message = str(excinfo.value)
    assert "raised" in message
    assert "no pair" not in message  # the genuine-no-pair wording is a different cause
    assert any("Round 1 failed" in w for w in excinfo.value.warnings)
    assert any("Round 2 failed" in w for w in excinfo.value.warnings)


@pytest.mark.asyncio
async def test_never_paired_run_raises():
    """A roster that never pairs across every round is a failed debate, not a silent one."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)
    synth.synthesize.return_value = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    topo.compute_round_pairs.return_value = []
    orch = _orch(synth, topo, society_memory, verdict_synth)
    config = DebateConfig(max_agents=5, max_rounds=2, max_new_agents_per_round=0)

    with pytest.raises(SocietyNotDebatableError, match="no pair"):
        await orch.run("q", "ds1", config, AsyncMock())

    assert topo.compute_round_pairs.await_count == 2  # every round was attempted
    verdict_synth.asynthesize.assert_not_called()


@pytest.mark.asyncio
async def test_check_convergence_domimant_stance_threshold():
    """_check_convergence returns True when dominant stance >= 80% of turns."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)

    profiles = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    synth.synthesize.return_value = profiles
    topo.compute_round_pairs.return_value = [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    verdict_synth.asynthesize.return_value = _make_verdict()

    # Build RoundResults with controlled turn stances so we can test
    # _check_convergence directly without wiring through the full LLM stack.
    alice_turns = [
        _make_turn("1", "Alice", "POSITIVE"),
        _make_turn("1", "Alice", "POSITIVE"),
        _make_turn("1", "Alice", "POSITIVE"),
        _make_turn("1", "Alice", "POSITIVE"),
        _make_turn("1", "Alice", "POSITIVE"),
        _make_turn("1", "Alice", "POSITIVE"),
        _make_turn("1", "Alice", "POSITIVE"),
        _make_turn("1", "Alice", "POSITIVE"),
    ]
    bob_turns = [
        _make_turn("2", "Bob", "POSITIVE"),
        _make_turn("2", "Bob", "POSITIVE"),
    ]

    pair = CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)

    # 8 POSITIVE from Alice + 2 POSITIVE from Bob = 100% dominant stance
    r1_turns = alice_turns[:8] + bob_turns[:1]
    r2_turns = alice_turns[8:] + bob_turns[1:]
    r1 = RoundResult(round_num=1, turns=r1_turns, pairs=[pair])
    r2 = RoundResult(round_num=2, turns=r2_turns, pairs=[pair])

    orchestrator = DebateOrchestrator(
        profile_synthesizer=synth,
        topology=topo,
        llm_runner=llm_runner,
        verdict_synthesizer=verdict_synth,
        society_memory=society_memory,
    )

    # Test _check_convergence directly
    assert orchestrator._check_convergence([r1], profiles) is False  # < 2 rounds
    assert orchestrator._check_convergence([r1, r2], profiles) is True  # 100% dominant


@pytest.mark.asyncio
async def test_commit_failure_degrades_to_warning():
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)
    synth.synthesize.return_value = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    topo.compute_round_pairs.side_effect = lambda *a, **kw: [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    verdict_synth.asynthesize.return_value = _make_verdict()
    society_memory.commit_round.side_effect = RuntimeError("db down")
    llm_runner.gather = MagicMock(side_effect=lambda *a, **kw: _AsyncEmptyIter())

    orchestrator = DebateOrchestrator(
        profile_synthesizer=synth,
        topology=topo,
        llm_runner=llm_runner,
        verdict_synthesizer=verdict_synth,
        society_memory=society_memory,
    )
    result = await orchestrator.run(
        "q", "ds1", DebateConfig(max_agents=5, max_rounds=1), AsyncMock()
    )
    assert any("commit failed" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_commit_failure_first_round_does_not_abort_loop():
    """A commit failure on round 1 degrades to a warning; round 2 still runs and commits."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)
    synth.synthesize.return_value = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    topo.compute_round_pairs.side_effect = lambda *a, **kw: [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    verdict_synth.asynthesize.return_value = _make_verdict()
    llm_runner.gather = MagicMock(side_effect=lambda *a, **kw: _AsyncEmptyIter())
    # Round 1 blows up, round 2 commits fine — the loop must survive the first.
    society_memory.commit_round.side_effect = [RuntimeError("db down"), _ok_receipt()]

    orchestrator = DebateOrchestrator(
        profile_synthesizer=synth,
        topology=topo,
        llm_runner=llm_runner,
        verdict_synthesizer=verdict_synth,
        society_memory=society_memory,
    )
    config = DebateConfig(max_agents=5, max_rounds=2)
    ws_broadcast = AsyncMock()
    result = await orchestrator.run("q", "ds1", config, ws_broadcast)

    assert result.rounds_executed == config.max_rounds
    assert any("Round 1: commit failed" in w for w in result.warnings)
    assert not any("Round 2: commit failed" in w for w in result.warnings)
    # Round 2's successful commit was broadcast — proof the loop reached it.
    sent = [c.args[0] for c in ws_broadcast.call_args_list if c.args]
    assert any(m.get("type") == "commit" for m in sent)


@pytest.mark.asyncio
async def test_convergence_uses_config_threshold():
    synth, topo, llm_runner, verdict_synth = (
        AsyncMock(spec=ProfileSynthesizer),
        AsyncMock(spec=CommunicationTopology),
        MagicMock(spec=BatchedLLMRunner),
        MagicMock(spec=VerdictSynthesizer),
    )
    profiles = [_make_profile(1, "Alice")]
    synth.synthesize.return_value = profiles
    topo.compute_round_pairs.side_effect = lambda *a, **kw: [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    verdict_synth.asynthesize.return_value = _make_verdict()
    llm_runner.gather = MagicMock(side_effect=lambda *a, **kw: _AsyncEmptyIter())
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)
    orchestrator = DebateOrchestrator(
        profile_synthesizer=synth,
        topology=topo,
        llm_runner=llm_runner,
        verdict_synthesizer=verdict_synth,
        society_memory=society_memory,
    )
    # 100% dominant on last 2 rounds → converged with low threshold...
    t = _make_turn("1", "Alice", "POSITIVE")
    r1 = RoundResult(round_num=1, turns=[t], pairs=[])
    r2 = RoundResult(round_num=2, turns=[t], pairs=[])
    assert (
        orchestrator._check_convergence(
            [r1, r2], profiles, config=DebateConfig(convergence_threshold=0.8)
        )
        is True
    )
    # ...and a 50%-dominant mix is rejected at 0.8 but accepted at 0.4
    n = _make_turn("1", "Alice", "NEGATIVE")
    r2b = RoundResult(round_num=2, turns=[t, n], pairs=[])
    assert (
        orchestrator._check_convergence(
            [r1, r2b], profiles, config=DebateConfig(convergence_threshold=0.8)
        )
        is False
    )
    assert (
        orchestrator._check_convergence(
            [r1, r2b], profiles, config=DebateConfig(convergence_threshold=0.4)
        )
        is True
    )


def _orch(synth, topo, society_memory, verdict_synth=None, llm_runner=None):
    if verdict_synth is None:
        verdict_synth = MagicMock(spec=VerdictSynthesizer)
        # run() awaits asynthesize; an unconfigured AsyncMock cannot yield verdict fields.
        verdict_synth.asynthesize.return_value = _make_verdict()
    return DebateOrchestrator(
        profile_synthesizer=synth,
        topology=topo,
        llm_runner=llm_runner or MagicMock(spec=BatchedLLMRunner),
        verdict_synthesizer=verdict_synth,
        society_memory=society_memory,
    )


@pytest.mark.asyncio
async def test_activation_pulls_in_candidates_after_commit():
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)
    # Explicit successful receipt: an unset AsyncMock return degrades to the commit-failed branch.
    society_memory.commit_round.return_value = _ok_receipt()
    synth.synthesize.return_value = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    new_profile = _make_profile(2, "Carl")
    synth.synthesize_from_names = AsyncMock(return_value=[new_profile])
    topo.compute_round_pairs.side_effect = lambda *a, **kw: [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    topo.find_activation_candidates = AsyncMock(
        return_value=[
            ActivationCandidate(
                agent_name="Carl",
                shared_entities=["carbon"],
                reason="mentioned entity in the debate",
            )
        ]
    )
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    llm_runner.gather = MagicMock(side_effect=lambda *a, **kw: _AsyncEmptyIter())
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    verdict_synth.asynthesize.return_value = _make_verdict()

    ws_calls = []

    async def ws(msg):
        ws_calls.append(msg)

    orch = _orch(synth, topo, society_memory, verdict_synth, llm_runner)
    result = await orch.run("q", "ds1", DebateConfig(max_agents=5, max_rounds=1), ws)

    synth.synthesize_from_names.assert_awaited_once()
    assert any(m.get("type") == "activation" for m in ws_calls)
    assert any("activated" in w for w in result.warnings)
    # F41.1: this test must not silently take the degraded commit branch either
    assert any(m.get("type") == "commit" for m in ws_calls)
    assert not any("commit failed" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_no_activation_event_when_no_candidate_resolves():
    """Candidates found but none resolvable → roster unchanged, so nothing was activated."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)
    society_memory.commit_round.return_value = _ok_receipt()
    synth.synthesize.return_value = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    synth.synthesize_from_names = AsyncMock(return_value=[])
    topo.compute_round_pairs.side_effect = lambda *a, **kw: [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    topo.find_activation_candidates = AsyncMock(
        return_value=[
            ActivationCandidate(
                agent_name="Carl",
                shared_entities=["carbon"],
                reason="mentioned entity in the debate",
            )
        ]
    )
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    llm_runner.gather = MagicMock(side_effect=lambda *a, **kw: _AsyncEmptyIter())
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    verdict_synth.asynthesize.return_value = _make_verdict()

    ws_calls = []

    async def ws(msg):
        ws_calls.append(msg)

    orch = _orch(synth, topo, society_memory, verdict_synth, llm_runner)
    result = await orch.run("q", "ds1", DebateConfig(max_agents=5, max_rounds=1), ws)

    synth.synthesize_from_names.assert_awaited_once()
    assert not any(m.get("type") == "activation" for m in ws_calls)
    assert not any("activated" in w for w in result.warnings)
    assert "a joining participant could not be profiled" in result.warnings


@pytest.mark.asyncio
async def test_an_activation_failure_warning_names_no_exception_class():
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)
    society_memory.commit_round.return_value = _ok_receipt()
    synth.synthesize.return_value = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    synth.synthesize_from_names = AsyncMock(side_effect=RuntimeError("socket reset by peer"))
    topo.compute_round_pairs.side_effect = lambda *a, **kw: [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    topo.find_activation_candidates = AsyncMock(
        return_value=[
            ActivationCandidate(agent_name="Carl", shared_entities=["carbon"], reason="mentioned entity in the debate")
        ]
    )
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    llm_runner.gather = MagicMock(side_effect=lambda *a, **kw: _AsyncEmptyIter())
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    verdict_synth.asynthesize.return_value = _make_verdict()

    orch = _orch(synth, topo, society_memory, verdict_synth, llm_runner)
    result = await orch.run("q", "ds1", DebateConfig(max_agents=5, max_rounds=1), AsyncMock())

    assert "Round 1: activation failed" in result.warnings
    assert not any("RuntimeError" in w or "socket" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_metering_error_from_activation_propagates_and_is_not_a_warning():
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)
    society_memory.commit_round.return_value = _ok_receipt()
    synth.synthesize.return_value = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    synth.synthesize_from_names = AsyncMock(side_effect=MeteringError("hold"))
    topo.compute_round_pairs.side_effect = lambda *a, **kw: [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    topo.find_activation_candidates = AsyncMock(
        return_value=[
            ActivationCandidate(
                agent_name="Carl",
                shared_entities=["carbon"],
                reason="mentioned entity in the debate",
            )
        ]
    )
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    llm_runner.gather = MagicMock(side_effect=lambda *a, **kw: _AsyncEmptyIter())
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    verdict_synth.asynthesize.return_value = _make_verdict()

    async def ws(msg):
        return None

    orch = _orch(synth, topo, society_memory, verdict_synth, llm_runner)
    with pytest.raises(MeteringError):
        await orch.run("q", "ds1", DebateConfig(max_agents=5, max_rounds=1), ws)


@pytest.mark.asyncio
async def test_activation_disabled_by_config():
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)
    # Explicit successful receipt: an unset AsyncMock return degrades to the commit-failed branch.
    society_memory.commit_round.return_value = _ok_receipt()
    synth.synthesize.return_value = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    synth.synthesize_from_names = AsyncMock(return_value=[])
    topo.compute_round_pairs.side_effect = lambda *a, **kw: [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    topo.find_activation_candidates = AsyncMock(
        return_value=[ActivationCandidate(agent_name="Carl")]
    )
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    llm_runner.gather = MagicMock(side_effect=lambda *a, **kw: _AsyncEmptyIter())
    orch = _orch(synth, topo, society_memory)

    config = DebateConfig(max_agents=5, max_rounds=1, max_new_agents_per_round=0)
    ws_broadcast = AsyncMock()
    await orch.run("q", "ds1", config, ws_broadcast)
    topo.find_activation_candidates.assert_not_awaited()
    synth.synthesize_from_names.assert_not_awaited()
    # F41.1: activation is off, but the commit path is still exercised — not silently degraded
    sent = [c.args[0] for c in ws_broadcast.call_args_list if c.args]
    assert any(m.get("type") == "commit" for m in sent)


@pytest.mark.asyncio
async def test_no_pair_round_attempts_activation_bootstrap():
    """A round with no pairs still tries to grow the roster — the bootstrap path."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)
    society_memory.commit_round.return_value = _ok_receipt()
    society_memory.read_snapshot.return_value = SocietySnapshot(round=1)
    synth.synthesize.return_value = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    synth.synthesize_from_names = AsyncMock(return_value=[_make_profile(3, "Carl")])
    topo.find_activation_candidates = AsyncMock(
        side_effect=[
            [
                ActivationCandidate(
                    agent_name="Carl",
                    shared_entities=["carbon"],
                    reason="shares entities",
                )
            ],
            [],  # round 2: Carl is a participant now — no more joiners
        ]
    )
    topo.compute_round_pairs = AsyncMock(
        side_effect=lambda profiles, **kw: (
            # Real pairing depends on who is in the roster: round 2 can only pair
            # with Carl if round 1 grew it. A roster that never grows pairs nothing.
            [
                CommPair(
                    agent_a="Alice",
                    agent_b="Carl",
                    shared_entities=["carbon"],
                    score=0.5,
                )
            ]
            if any(p.identity.name == "Carl" for p in profiles)
            else []
        )
    )
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    llm_runner.gather = MagicMock(side_effect=lambda *a, **kw: _AsyncEmptyIter())
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    verdict_synth.asynthesize.return_value = _make_verdict()
    ws_calls = []

    async def ws(msg):
        ws_calls.append(msg)

    orch = _orch(synth, topo, society_memory, verdict_synth, llm_runner)
    result = await orch.run("q", "ds1", DebateConfig(max_agents=5, max_rounds=2), ws)

    synth.synthesize_from_names.assert_awaited_once()
    assert synth.synthesize_from_names.await_args.kwargs["names"] == ["Carl"]
    assert topo.compute_round_pairs.await_count == 2  # round 2 ran after growth
    assert result.rounds_executed == 1
    assert any(m.get("type") == "activation" for m in ws_calls)


@pytest.mark.asyncio
async def test_run_threads_intent_to_round_runner_and_result():
    """S3: the run's intent reaches the prompt builder and is exposed on the result."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)
    society_memory.commit_round.return_value = _ok_receipt()
    synth.synthesize.return_value = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    topo.compute_round_pairs.return_value = [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    llm_runner.gather = MagicMock(side_effect=lambda *a, **kw: _AsyncEmptyIter())
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    verdict_synth.asynthesize.return_value = _make_verdict()
    intent = QueryIntent(
        direct_keywords=["carbon"],
        latent_sectors=[],
        search_perspectives=[],
        core_question="Tax carbon?",
        stance_axis="Support = tax it.",
    )

    orch = _orch(synth, topo, society_memory, verdict_synth, llm_runner)
    with patch("src.simulation.orchestrator.RoundRunner") as patched_rr_class:
        patched_rr_instance = MagicMock()
        patched_rr_instance.execute_round = AsyncMock(
            return_value=RoundResult(round_num=1, turns=[], pairs=[])
        )
        patched_rr_class.return_value = patched_rr_instance

        result = await orch.run(
            "q",
            "ds1",
            DebateConfig(max_agents=5, max_rounds=1),
            AsyncMock(),
            intent=intent,
        )

        assert patched_rr_class.call_args.kwargs["intent"] is intent
    assert result.intent is intent


@pytest.mark.asyncio
async def test_run_threads_query_and_context_and_returns_the_narrative():
    """T3: the run's query + user context reach synthesis; the narrative is returned."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)
    society_memory.commit_round.return_value = _ok_receipt()
    synth.synthesize.return_value = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    topo.compute_round_pairs.return_value = [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    llm_runner.gather = MagicMock(side_effect=lambda *a, **kw: _AsyncEmptyIter())
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    verdict = _make_verdict()
    verdict.narrative = "## Recommendation\nExpand, cautiously."
    verdict.dissenting_views = [{"stance": "NEGATIVE", "view": "too soon"}]
    verdict.evidence = [{"entity": "Steel tariffs", "claim": "raises cost"}]
    verdict_synth.asynthesize.return_value = verdict

    orch = _orch(synth, topo, society_memory, verdict_synth, llm_runner)
    result = await orch.run(
        "Should we expand to Europe?",
        "ds1",
        DebateConfig(max_agents=5, max_rounds=1),
        AsyncMock(),
        context={"budget": "limited"},
    )

    call_kwargs = verdict_synth.asynthesize.await_args.kwargs
    assert call_kwargs["query"] == "Should we expand to Europe?"
    assert "limited" in call_kwargs["scenario"]

    assert result.narrative == "## Recommendation\nExpand, cautiously."
    assert result.dissenting_views == [{"stance": "NEGATIVE", "view": "too soon"}]
    assert result.evidence == [{"entity": "Steel tariffs", "claim": "raises cost"}]


@pytest.mark.asyncio
async def test_run_without_context_still_synthesizes():
    """T3: context is optional — query alone must still drive synthesis."""
    orch = _stage_ready_orch(max_rounds=1)
    result = await orch.run(
        "q",
        "ds1",
        DebateConfig(max_agents=5, max_rounds=1),
        AsyncMock(),
    )
    assert (
        result.narrative == orch._verdict_synthesizer.asynthesize.return_value.narrative
    )


@pytest.mark.asyncio
async def test_run_without_intent_exposes_none():
    """Backward compatibility: older callers pass no intent and the run still completes."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)
    society_memory.commit_round.return_value = _ok_receipt()
    synth.synthesize.return_value = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    topo.compute_round_pairs.return_value = [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    llm_runner.gather = MagicMock(side_effect=lambda *a, **kw: _AsyncEmptyIter())
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    verdict_synth.asynthesize.return_value = _make_verdict()

    orch = _orch(synth, topo, society_memory, verdict_synth, llm_runner)
    result = await orch.run(
        "q", "ds1", DebateConfig(max_agents=5, max_rounds=1), AsyncMock()
    )
    assert result.intent is None
    assert result.rounds_executed == 1


"""S9: real stage events emitted from the orchestrator (P5-T1)."""


def _stage_spy() -> tuple[list[dict], object]:
    """(events, emitter) — an emitter that records what it is handed."""
    events: list[dict] = []

    async def emit(event):
        events.append(event)

    return events, emit


def _stage_ready_orch(max_rounds: int = 3, profiles=None):
    """An orchestrator whose stubbed run executes `max_rounds` real rounds."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)
    society_memory.commit_round.return_value = _ok_receipt()
    synth.synthesize.return_value = (
        profiles
        if profiles is not None
        else [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    )
    topo.compute_round_pairs.side_effect = lambda *a, **kw: [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    llm_runner.gather = MagicMock(side_effect=lambda *a, **kw: _AsyncEmptyIter())
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    verdict_synth.asynthesize.return_value = _make_verdict()
    return _orch(synth, topo, society_memory, verdict_synth, llm_runner)


@pytest.mark.asyncio
async def test_stage_events_follow_the_documented_sequence():
    """A WS consumer sees every real transition, in order, with a monotonic index."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)
    society_memory.commit_round.return_value = _ok_receipt()
    synth.synthesize.return_value = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    topo.compute_round_pairs.side_effect = lambda *a, **kw: [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    verdict_synth.asynthesize.return_value = _make_verdict()
    orch = _orch(synth, topo, society_memory, verdict_synth)
    events, emit = _stage_spy()

    pair = CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    with patch("src.simulation.orchestrator.RoundRunner") as rr_cls:
        rr_instance = MagicMock()
        # An even split every round keeps the window share at 0.5, so the loop runs all three rounds.
        rr_instance.execute_round = AsyncMock(
            side_effect=lambda **kw: RoundResult(
                round_num=kw["round_num"],
                turns=[_make_turn("1", "Alice"), _make_turn("2", "Bob", "NEGATIVE")],
                pairs=[pair],
            )
        )
        rr_cls.return_value = rr_instance

        result = await orch.run(
            "q",
            "ds1",
            DebateConfig(max_agents=5, max_rounds=3),
            AsyncMock(),
            on_stage=emit,
        )

    assert [(e["stage"], e.get("round")) for e in events] == [
        ("intake", None),
        ("selection", None),
        ("synthesis", None),
        ("round", 1),
        ("round", 2),
        ("round", 3),
        ("convergence", None),
        ("verdict", None),
    ]
    assert all(e["type"] == "stage" for e in events)
    assert [e["index"] for e in events] == list(range(len(events)))
    assert events[0]["query"] == "q"
    assert events[2]["agents"] == 2
    # the round event reports that round's own execution
    assert (events[3]["round"], events[3]["pairs"], events[3]["turns"]) == (1, 1, 2)
    assert events[4]["round"] == 2 and events[5]["round"] == 3
    assert events[-2]["converged"] is result.converged
    assert events[-2]["rounds_executed"] == result.rounds_executed == 3


@pytest.mark.asyncio
async def test_no_emitter_and_failing_emitter_both_leave_the_run_intact():
    """Observability degrades, the run never does: None → no events; raising → logged."""
    orch = _stage_ready_orch(max_rounds=1)
    result = await orch.run(
        "q", "ds1", DebateConfig(max_agents=5, max_rounds=1), AsyncMock(), on_stage=None
    )
    assert result.rounds_executed == 1

    async def exploding_emitter(event):
        raise RuntimeError("socket closed")

    result = await orch.run(
        "q",
        "ds1",
        DebateConfig(max_agents=5, max_rounds=1),
        AsyncMock(),
        on_stage=exploding_emitter,
    )
    assert result.rounds_executed == 1
    assert result.verdict == "Test verdict."


"""P5: the run streams each built profile and the seated names, and the round's weights."""


def _orchestrator_with(synth, topo, llm_runner, verdict_synth, society_memory):
    return DebateOrchestrator(
        profile_synthesizer=synth,
        topology=topo,
        llm_runner=llm_runner,
        verdict_synthesizer=verdict_synth,
        society_memory=society_memory,
    )


@pytest.mark.asyncio
async def test_agent_events_are_broadcast_in_order_without_a_selection_event():
    """Each built profile streams in order; no selection event is streamed."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)

    profiles = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]

    async def fake_synthesize(**kwargs):
        for index, profile in enumerate(profiles, start=1):
            await kwargs["on_profile"](profile, index, len(profiles))
        return profiles

    synth.synthesize.side_effect = fake_synthesize
    topo.compute_round_pairs.return_value = [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    verdict_synth.asynthesize.return_value = _make_verdict()
    society_memory.commit_round.return_value = _ok_receipt()

    orchestrator = _orchestrator_with(
        synth, topo, llm_runner, verdict_synth, society_memory
    )
    ws_calls = []

    async def fake_ws(msg):
        ws_calls.append(msg)

    with patch("src.simulation.orchestrator.RoundRunner") as rr_cls:
        rr_instance = MagicMock()
        rr_instance.execute_round = AsyncMock(
            return_value=RoundResult(round_num=1, turns=[], pairs=[])
        )
        rr_cls.return_value = rr_instance

        await orchestrator.run(
            "test query", "ds1", DebateConfig(max_agents=5, max_rounds=1), fake_ws
        )

    types = [m["type"] for m in ws_calls]
    assert "selection" not in types
    agents = [m for m in ws_calls if m["type"] == "agent"]
    assert [m["index"] for m in agents] == [1, 2]
    assert all(m["total"] == 2 for m in agents)
    assert agents[0]["profile"]["name"] == "Alice"
    assert set(agents[0]["profile"]) == set(AgentView.model_fields)


@pytest.mark.asyncio
async def test_round_events_carry_consensus_weights():
    """Each round exposes the per-stance weight share — the convergence tape's input."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)

    profiles = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    synth.synthesize.return_value = profiles
    topo.compute_round_pairs.return_value = [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    verdict_synth.asynthesize.return_value = _make_verdict()
    society_memory.commit_round.return_value = _ok_receipt()

    rounds = [
        RoundResult(
            round_num=1,
            pairs=[
                CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
            ],
            turns=[
                _make_turn("id-1", "Alice", "POSITIVE", strength=0.6),
                _make_turn("id-2", "Bob", "NEGATIVE", strength=0.4),
            ],
        )
    ]

    with patch("src.simulation.orchestrator.RoundRunner") as patched_rr_class:
        instance = MagicMock()
        instance.execute_round = AsyncMock(side_effect=rounds)
        patched_rr_class.return_value = instance

        orchestrator = _orchestrator_with(
            synth, topo, llm_runner, verdict_synth, society_memory
        )
        ws_calls = []

        async def fake_ws(msg):
            ws_calls.append(msg)

        await orchestrator.run(
            "test query", "ds1", DebateConfig(max_agents=5, max_rounds=1), fake_ws
        )

    round_msg = next(m for m in ws_calls if m["type"] == "round")
    assert round_msg["consensus"]["weights"]["POSITIVE"] == 0.6
    assert round_msg["consensus"]["weights"]["NEGATIVE"] == 0.4


@pytest.mark.asyncio
async def test_failed_commit_is_still_broadcast():
    """A failed commit is an event (the stream shows the warning), not a swallowed error."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)

    profiles = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    synth.synthesize.return_value = profiles
    topo.compute_round_pairs.return_value = [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    verdict_synth.asynthesize.return_value = _make_verdict()
    society_memory.commit_round.return_value = {
        "round": 1,
        "opinions": 0,
        "edges": 0,
        "failed": True,
        "error": "neo4j down",
    }

    rounds = [
        RoundResult(
            round_num=1,
            pairs=[
                CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
            ],
            turns=[_make_turn("id-1", "Alice")],
        )
    ]

    with patch("src.simulation.orchestrator.RoundRunner") as patched_rr_class:
        instance = MagicMock()
        instance.execute_round = AsyncMock(side_effect=rounds)
        patched_rr_class.return_value = instance

        orchestrator = _orchestrator_with(
            synth, topo, llm_runner, verdict_synth, society_memory
        )
        ws_calls = []

        async def fake_ws(msg):
            ws_calls.append(msg)

        result = await orchestrator.run(
            "test query", "ds1", DebateConfig(max_agents=5, max_rounds=1), fake_ws
        )

    commit_msg = next(m for m in ws_calls if m["type"] == "commit")
    assert commit_msg["failed"] is True
    assert any("commit failed" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_convergence_stage_carries_share_and_threshold():
    """The convergence event exposes the decision's inputs, not just its outcome."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)

    profiles = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    synth.synthesize.return_value = profiles
    topo.compute_round_pairs.return_value = [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    verdict_synth.asynthesize.return_value = _make_verdict()
    society_memory.commit_round.return_value = _ok_receipt()

    rounds = [
        RoundResult(
            round_num=1,
            pairs=[
                CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
            ],
            turns=[
                _make_turn("id-1", "Alice", "POSITIVE"),
                _make_turn("id-2", "Bob", "NEGATIVE"),
            ],
        )
    ]

    with patch("src.simulation.orchestrator.RoundRunner") as patched_rr_class:
        instance = MagicMock()
        instance.execute_round = AsyncMock(side_effect=rounds)
        patched_rr_class.return_value = instance

        orchestrator = _orchestrator_with(
            synth, topo, llm_runner, verdict_synth, society_memory
        )
        ws_calls = []

        async def fake_ws(msg):
            ws_calls.append(msg)

        await orchestrator.run(
            "test query",
            "ds1",
            DebateConfig(max_agents=5, max_rounds=1),
            fake_ws,
            on_stage=fake_ws,
        )

    stage_event = next(
        m for m in ws_calls if m["type"] == "stage" and m["stage"] == "convergence"
    )
    assert stage_event["threshold"] == 0.8
    assert "share" in stage_event


@pytest.mark.asyncio
async def test_result_carries_the_verdict_payload_for_the_ui():
    """`complete` needs the full verdict: confidence, cluster breakdown, entities (§12.3 item 5)."""
    from src.simulation.pair_turn import ClusterSummary

    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)

    synth.synthesize.return_value = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    topo.compute_round_pairs.return_value = [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    # Explicit successful receipt: an unset AsyncMock return degrades to the commit-failed branch.
    society_memory.commit_round.return_value = _ok_receipt()
    verdict = _make_verdict()
    verdict.cluster_details = {
        Stance.POSITIVE: ClusterSummary(
            stance=Stance.POSITIVE,
            count=2,
            total_weight=0.6,
            avg_confidence=0.7,
            avg_conviction=0.6,
            agents=["Alice"],
        )
    }
    verdict.supporting_entities = ["Steel tariffs"]
    verdict.opposing_entities = ["Entry cost"]
    verdict.provenance_by_claim = {
        "Steel tariffs": [
            ProvenanceLink(
                doc_id="d1",
                title="Trade Report",
                breadcrumb="p3",
                chunk_id=uuid.uuid4(),
            )
        ]
    }
    verdict_synth.asynthesize.return_value = verdict

    orchestrator = _orchestrator_with(
        synth, topo, llm_runner, verdict_synth, society_memory
    )
    ws_calls = []

    async def fake_ws(msg):
        ws_calls.append(msg)

    with patch("src.simulation.orchestrator.RoundRunner") as rr_cls:
        rr_instance = MagicMock()
        rr_instance.execute_round = AsyncMock(
            return_value=RoundResult(round_num=1, turns=[], pairs=[])
        )
        rr_cls.return_value = rr_instance

        result = await orchestrator.run(
            "test query", "ds1", DebateConfig(max_agents=5, max_rounds=1), fake_ws
        )

    assert result.confidence_score == 0.9
    assert result.cluster_details["POSITIVE"]["count"] == 2
    assert result.cluster_details["POSITIVE"]["stance"] == "POSITIVE"
    assert result.supporting_entities == ["Steel tariffs"]
    assert result.opposing_entities == ["Entry cost"]
    # Step 8 output must reach the delivered result, JSON-safe.
    assert result.provenance_by_claim["Steel tariffs"][0]["title"] == "Trade Report"
    assert isinstance(result.provenance_by_claim["Steel tariffs"][0]["chunk_id"], str)


@pytest.mark.asyncio
async def test_metering_error_is_not_absorbed_by_the_round_loop():
    """R9: a metering failure escapes the round loop instead of being a warning."""
    from src.billing.metering import MeteringError

    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)

    synth.synthesize.return_value = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    topo.compute_round_pairs.return_value = [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    verdict_synth.asynthesize.return_value = _make_verdict()
    llm_runner.gather = MagicMock(
        side_effect=MeteringError("metering failed: usage missing")
    )
    society_memory.commit_round.return_value = _ok_receipt()

    orchestrator = DebateOrchestrator(
        profile_synthesizer=synth,
        topology=topo,
        llm_runner=llm_runner,
        verdict_synthesizer=verdict_synth,
        society_memory=society_memory,
    )

    with pytest.raises(MeteringError):
        await orchestrator.run(
            "test query", "ds1", DebateConfig(max_agents=5, max_rounds=3), AsyncMock()
        )


# ---- client-visible warnings name no exception class (every path that formats one) -----------


def _names_no_exception_class(warnings: list[str]) -> bool:
    return not any(re.search(r"\b\w+(Error|Exception)\b", w) for w in warnings)


async def _two_rounds(society_memory, topo, *, pairs_side_effect=None):
    """Two rounds with one pair each, so round 2 reads a snapshot and the self history."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    synth.synthesize.return_value = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    synth.synthesize_from_names = AsyncMock(return_value=[])
    if pairs_side_effect is not None:
        topo.compute_round_pairs.side_effect = pairs_side_effect
    else:
        topo.compute_round_pairs.side_effect = lambda *a, **kw: [
            CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
        ]
    topo.find_activation_candidates = AsyncMock(return_value=[])
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    llm_runner.gather = MagicMock(side_effect=lambda *a, **kw: _AsyncEmptyIter())
    orch = _orch(synth, topo, society_memory, None, llm_runner)
    return await orch.run("q", "ds1", DebateConfig(max_agents=5, max_rounds=2), AsyncMock())


def _society(**overrides) -> AsyncMock:
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)
    society_memory.commit_round.return_value = _ok_receipt()
    society_memory.read_self_history.return_value = []
    for name, value in overrides.items():
        getattr(society_memory, name).side_effect = value
    return society_memory


@pytest.mark.asyncio
async def test_a_snapshot_read_failure_warns_without_an_exception_class():
    result = await _two_rounds(
        _society(read_snapshot=RuntimeError("db down")), AsyncMock(spec=CommunicationTopology)
    )

    assert ("Round 2: society snapshot read failed" in result.warnings, _names_no_exception_class(result.warnings)) == (
        True,
        True,
    )


@pytest.mark.asyncio
async def test_a_commit_failure_warns_without_an_exception_class():
    result = await _two_rounds(
        _society(commit_round=RuntimeError("db down")), AsyncMock(spec=CommunicationTopology)
    )

    assert ("Round 1: commit failed" in result.warnings, _names_no_exception_class(result.warnings)) == (True, True)


@pytest.mark.asyncio
async def test_a_failed_round_warns_without_an_exception_class():
    calls = []

    def pairs_failing_once(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("topology down")
        return [CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)]

    result = await _two_rounds(
        _society(),
        AsyncMock(spec=CommunicationTopology),
        pairs_side_effect=pairs_failing_once,
    )

    assert ("Round 1 failed" in result.warnings, _names_no_exception_class(result.warnings)) == (True, True)


@pytest.mark.asyncio
async def test_a_self_history_failure_warns_without_an_exception_class():
    result = await _two_rounds(
        _society(read_self_history=RuntimeError("db down")), AsyncMock(spec=CommunicationTopology)
    )

    assert ("Round 2: self history read failed" in result.warnings, _names_no_exception_class(result.warnings)) == (
        True,
        True,
    )


def _rec(name: str, status: str = "published"):
    """A stand-in record: the orchestrator reads only node.name, the seam only passes it on."""
    return SimpleNamespace(node=SimpleNamespace(name=name), status=status)


def _seam_orchestrator(synth, topo=None):
    return DebateOrchestrator(
        profile_synthesizer=synth,
        topology=topo or AsyncMock(spec=CommunicationTopology),
        llm_runner=MagicMock(spec=BatchedLLMRunner),
        verdict_synthesizer=MagicMock(spec=VerdictSynthesizer),
        society_memory=AsyncMock(spec=SocietyMemory),
    )


@pytest.mark.asyncio
async def test_records_reach_the_seam_even_when_synthesis_raises():
    from src.simulation.ranking import NoAgentsDerivableError

    synth = AsyncMock(spec=ProfileSynthesizer)

    async def synthesize_then_fail(**kwargs):
        kwargs["records"].append(_rec("Lumen", "rejected"))
        raise NoAgentsDerivableError("no profile could be seated")

    synth.synthesize.side_effect = synthesize_then_fail
    on_records = AsyncMock()

    with pytest.raises(NoAgentsDerivableError):
        await _seam_orchestrator(synth).run(
            "test query", "ds1", DebateConfig(max_agents=5, max_rounds=1), AsyncMock(), on_records=on_records
        )

    on_records.assert_awaited_once()
    assert [r.node.name for r in on_records.await_args.args[0]] == ["Lumen"]


@pytest.mark.asyncio
async def test_each_joiner_batch_reaches_the_seam_with_the_seats_already_taken():
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)
    society_memory.commit_round.return_value = _ok_receipt()

    async def synthesize(**kwargs):
        kwargs["records"].append(_rec("Alice"))
        return [_make_profile(1, "Alice"), _make_profile(2, "Bob")]

    async def synthesize_from_names(**kwargs):
        kwargs["records"].append(_rec("Carol"))
        return [_make_profile(3, "Carol")]

    synth.synthesize.side_effect = synthesize
    synth.synthesize_from_names.side_effect = synthesize_from_names
    topo.compute_round_pairs.return_value = [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    topo.find_activation_candidates.return_value = [
        SimpleNamespace(agent_name="Carol", shared_entities=[], reason="linked")
    ]
    verdict_synth.asynthesize.return_value = _make_verdict()
    llm_runner.gather = MagicMock(return_value=_AsyncEmptyIter())
    on_records = AsyncMock()

    orchestrator = DebateOrchestrator(
        profile_synthesizer=synth,
        topology=topo,
        llm_runner=llm_runner,
        verdict_synthesizer=verdict_synth,
        society_memory=society_memory,
    )
    await orchestrator.run(
        "test query", "ds1", DebateConfig(max_agents=5, max_rounds=1), AsyncMock(), on_records=on_records
    )

    assert [[r.node.name for r in call.args[0]] for call in on_records.await_args_list] == [
        ["Alice"],
        ["Carol"],
    ]
    assert synth.synthesize_from_names.await_args.kwargs["seat_offset"] == 2


@pytest.mark.asyncio
async def test_a_node_tried_in_the_initial_synthesis_is_not_drawn_as_a_joiner():
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)
    society_memory.commit_round.return_value = _ok_receipt()

    def record(name: str, status: str):
        return SimpleNamespace(node=SimpleNamespace(name=name), status=status)

    async def synthesize(**kwargs):
        kwargs["records"].extend([record("Lumen", "rejected"), record("Alice", "published")])
        return [_make_profile(1, "Alice"), _make_profile(2, "Bob")]

    async def synthesize_from_names(**kwargs):
        kwargs["records"].extend(record(name, "published") for name in kwargs["names"])
        return [_make_profile(3, name) for name in kwargs["names"]]

    synth.synthesize.side_effect = synthesize
    synth.synthesize_from_names.side_effect = synthesize_from_names
    topo.compute_round_pairs.return_value = [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    # The topology returns the rejected node again, as a graph neighbour of the debate would.
    topo.find_activation_candidates.return_value = [
        SimpleNamespace(agent_name="Lumen", shared_entities=[], reason="linked"),
        SimpleNamespace(agent_name="Carol", shared_entities=[], reason="linked"),
    ]
    verdict_synth.asynthesize.return_value = _make_verdict()
    llm_runner.gather = MagicMock(return_value=_AsyncEmptyIter())
    on_records = AsyncMock()

    await DebateOrchestrator(
        profile_synthesizer=synth,
        topology=topo,
        llm_runner=llm_runner,
        verdict_synthesizer=verdict_synth,
        society_memory=society_memory,
    ).run("test query", "ds1", DebateConfig(max_agents=5, max_rounds=1), AsyncMock(), on_records=on_records)

    assert synth.synthesize_from_names.await_args.kwargs["names"] == ["Carol"]
    handed = [[r.node.name for r in call.args[0]] for call in on_records.await_args_list]
    assert handed == [["Lumen", "Alice"], ["Carol"]]


# --- end to end: no provenance, evidence, reasoning or cite id reaches a client payload ---
#
# The run is the real path: a real ProfileSynthesizer over the fake graph and fake profile model,
# a seeded QueryIntent, a fake round gather and a fake verdict. Several brief markers never occur
# in a real run (no code path writes them), so each marker is also planted as a canary in the
# unprojected events and result, and the projection must remove it there.

_LEAK_QUESTION = "Should we enter Berlin?"
_LEAK_ENTITIES = [
    EntityNode(id="kestra", name="Kestra", label="Company", relevance_score=0.9),
    EntityNode(id="orbit", name="Orbit", label="Person", relevance_score=0.7),
    EntityNode(id="lumen", name="Lumen", label="Company", relevance_score=0.8),
]
_LEAK_CHUNK_ID = uuid.UUID("c0ffee00-0000-4000-8000-0000000000c1")
_LEAK_DOC_ID = "doc-market-memo"
# Every evidence sentence the fake graph serves, taken from the fixture's own chunks.
_EVIDENCE_SENTENCES = sorted(
    {
        sentence
        for hit in _chunks_for(_LEAK_ENTITIES).vector
        for sentence in re.split(r"(?<=\.)\s+", hit.text)
        if sentence
    }
)
_LEAK_MARKERS = (
    "chunk_id", "doc_id", "version_hash", "dossier_hash", "graph_snapshot", "summary_provenance",
    "source_evidence", "evidence", "REASONING", "[e1]", "llm_model", "anchors", "source_count",
)
# Markers a real run produces. The other six in _LEAK_MARKERS never occur in a run: they are
# guarded by their per-marker removal cases, not by the positive control.
_NATURAL_MARKERS = ("chunk_id", "doc_id", "dossier_hash", "evidence", "REASONING", "[e1]", "llm_model")
_TURN_REPLY = (
    "REASONING: the memo's pricing section decides it, privately.\n"
    "ANSWER: POSITIVE. The pilot rollout timing decides it."
)
_LEAK_INTENT = QueryIntent(
    direct_keywords=["Berlin", "pilot"],
    latent_sectors=["logistics"],
    search_perspectives=["Economic"],
    core_question="Should the company enter Berlin?",
    domain_tags=["economic"],
    entity_frame=["Kestra"],
    stance_axis="support means entering Berlin",
    extraction_confidence=0.82,
    llm_model="fixture-extraction-model",
    llm_provider="fixture-provider",
)


class _ReasoningLLM(FakeLLM):
    """The fake profile model: a private REASONING block ahead of each JSON reply, kept for the control."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.raw_replies: list[str] = []

    def _profile(self, name: str, user_prompt: str) -> str:
        reply = f"REASONING: {name} works through the memo privately first.\n" + super()._profile(
            name, user_prompt
        )
        self.raw_replies.append(reply)
        return reply


def _leak_verdict() -> DebateVerdict:
    """The verdict as the synthesiser hands it over, with the raw fields a client must not see."""
    return DebateVerdict(
        overall_stance=Stance.POSITIVE,
        confidence_score=0.9,
        supporting_entities=["Kestra"],
        opposing_entities=[],
        summary="Kestra and Orbit back the Berlin pilot.",
        cluster_details={},
        provenance_by_claim={
            "The pilot is priced per seat": [
                ProvenanceLink(
                    doc_id=_LEAK_DOC_ID,
                    title="Market memo",
                    breadcrumb="Pricing",
                    chunk_id=_LEAK_CHUNK_ID,
                )
            ]
        },
        rounds_executed=2,
        evidence=[
            {
                "entity": "Kestra",
                "claim": "The pilot is priced per seat",
                "quote": _EVIDENCE_SENTENCES[0],
                "chunk_id": str(_LEAK_CHUNK_ID),
            }
        ],
    )


async def _run_leak_debate() -> SimpleNamespace:
    """A real ProfileSynthesizer over the fake graph and fake profile model, one rejected candidate."""
    events: list[dict] = []
    records: list = []
    llm = _ReasoningLLM(fail={"Lumen"})

    async def ws_broadcast(event: dict) -> None:
        events.append(event)

    async def on_records(batch) -> None:
        records.extend(batch)

    async def gather(prompts):
        for prompt in prompts:
            yield PairResult(pair_id=prompt.pair_id, response=_TURN_REPLY)

    llm_runner = MagicMock(spec=BatchedLLMRunner)
    llm_runner.gather = MagicMock(side_effect=gather)
    topology = AsyncMock(spec=CommunicationTopology)
    topology.compute_round_pairs.return_value = [CommPair(agent_a="Kestra", agent_b="Orbit")]
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)
    society_memory.commit_round.return_value = _ok_receipt()
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    verdict_synth.asynthesize.return_value = _leak_verdict()
    orchestrator = DebateOrchestrator(
        profile_synthesizer=ProfileSynthesizer(
            persona_repo=_repo(), graph_context=FakeGraph(_LEAK_ENTITIES)
        ),
        topology=topology,
        llm_runner=llm_runner,
        verdict_synthesizer=verdict_synth,
        society_memory=society_memory,
    )

    # The job broadcasts the intent before the run (debate_api.py:312); the run is handed the same intent.
    events.append({"type": "intent", "intent": _LEAK_INTENT.model_dump()})
    result = await orchestrator.run(
        _LEAK_QUESTION,
        "ds1",
        DebateConfig(max_agents=2, max_rounds=2),
        ws_broadcast,
        llm_client=llm,
        intent=_LEAK_INTENT,
        on_records=on_records,
    )
    return SimpleNamespace(
        events=events, records=records, result=result, llm=llm, society_memory=society_memory
    )


def _as_text(payload) -> str:
    return json.dumps(payload, sort_keys=True, default=str)


def _result_payload(run: SimpleNamespace) -> dict:
    """The result as the job stores it: asdict, with the intent as model_dump (debate_api.py:403)."""
    payload = dataclasses.asdict(run.result)
    payload["intent"] = run.result.intent.model_dump() if run.result.intent else None
    return payload


def _projected(events: list[dict], result: dict) -> SimpleNamespace:
    """The projected stream and result, as text per surface, plus the verdict's evidence list."""
    stream = [event for event in map(project_event, events) if event is not None]
    projected = project_result(result)
    # `evidence` is a verdict key by contract (spec 4b): its items are narrowed to {entity, claim},
    # which an exact assertion checks. Top-level keys named `evidence` (the verdict in the result and
    # in a `complete` event) are renamed so the substring scan still covers every value they carry,
    # while the permitted key name itself is not counted as a leak.
    verdict_evidence = projected["evidence"]
    return SimpleNamespace(
        surfaces={
            "stream": _as_text([_scan_keys(event) for event in stream]),
            "result": _as_text(_scan_keys(projected)),
        },
        stream=stream,
        verdict_evidence=verdict_evidence,
    )


def _scan_keys(payload: dict) -> dict:
    return {("verdict_claims" if key == "evidence" else key): value for key, value in payload.items()}


_CANARY_CONTAINERS = ("profile", "intent")
_CANARY_ITEMS = ("evidence", "dissenting_views")


def _canaried(obj: dict, marker: str) -> dict:
    """A copy of one event or result dict with `marker` planted where the projection must drop it.

    It goes in as an unlisted top-level key with the marker as its value, and as an unlisted key
    inside every dict the projection narrows (profile, intent, evidence and dissent items, links).
    """
    out = copy.deepcopy(obj)
    out.setdefault(marker, marker)
    for key in _CANARY_CONTAINERS:
        if isinstance(out.get(key), dict):
            out[key][marker] = marker
    for key in _CANARY_ITEMS:
        for item in out.get(key) or []:
            if isinstance(item, dict):
                item[marker] = marker
    for links in (out.get("provenance_by_claim") or {}).values():
        for link in links or []:
            if isinstance(link, dict):
                link[marker] = marker
    return out


def _canaried_inputs(run: SimpleNamespace, marker: str) -> tuple[list[dict], dict]:
    """The unprojected events (plus a `complete` built from the result) and result, each with the canary."""
    result = _result_payload(run)
    events = [_canaried(event, marker) for event in run.events]
    events.append(_canaried({"type": "complete", **result}, marker))
    return events, _canaried(result, marker)


async def _client_payloads(run: SimpleNamespace) -> SimpleNamespace:
    """What a client can receive: the projected stream, the projected result and the roster."""
    projection = _projected(run.events, _result_payload(run))
    # Roster leg: the pure projection over the stored view, as read_roster builds it. The SQL read
    # itself (record -> 'view', published rows only) is DB-gated and not exercised here.
    published = [
        record.model_dump(mode="json")["view"] for record in run.records if record.status == "published"
    ]
    roster = [view.model_dump(mode="json") for view in roster_views(published)]
    surfaces = {**projection.surfaces, "roster": _as_text(roster)}
    types = {event["profile"].get("type") for event in projection.stream if event["type"] == "agent"}
    types |= {view["type"] for view in roster}
    return SimpleNamespace(surfaces=surfaces, verdict_evidence=projection.verdict_evidence, types=types)


@pytest.mark.asyncio
@pytest.mark.parametrize("marker", _LEAK_MARKERS, ids=_LEAK_MARKERS)
async def test_no_client_payload_carries_a_leak_marker(marker):
    payloads = await _client_payloads(await _run_leak_debate())

    assert [name for name, text in payloads.surfaces.items() if marker in text] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("marker", _LEAK_MARKERS, ids=_LEAK_MARKERS)
async def test_canary_marker_is_removed_by_the_projection(marker):
    events, result = _canaried_inputs(await _run_leak_debate(), marker)

    projection = _projected(events, result)

    assert [name for name, text in projection.surfaces.items() if marker in text] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("sentence", _EVIDENCE_SENTENCES, ids=_EVIDENCE_SENTENCES)
async def test_no_client_payload_carries_an_evidence_sentence(sentence):
    payloads = await _client_payloads(await _run_leak_debate())

    assert [name for name, text in payloads.surfaces.items() if sentence in text] == []


@pytest.mark.asyncio
async def test_no_client_agent_is_typed_entity():
    payloads = await _client_payloads(await _run_leak_debate())

    assert "Entity" not in payloads.types


@pytest.mark.asyncio
async def test_seated_agents_carry_the_fixture_labels():
    payloads = await _client_payloads(await _run_leak_debate())

    assert payloads.types == {"Company", "Person"}


@pytest.mark.asyncio
async def test_verdict_evidence_keeps_only_entity_and_claim():
    payloads = await _client_payloads(await _run_leak_debate())

    assert payloads.verdict_evidence == [{"entity": "Kestra", "claim": "The pilot is priced per seat"}]


@pytest.mark.asyncio
async def test_positive_control_every_marker_and_sentence_is_in_the_unprojected_data():
    run = await _run_leak_debate()
    raw_records = [record.model_dump(mode="json") for record in run.records]
    raw = _as_text(
        {
            "events": run.events,
            "result": _result_payload(run),
            "records": raw_records,
            "model_replies": run.llm.raw_replies,
        }
    )
    canaried = "".join(_as_text(_canaried_inputs(run, marker)) for marker in _LEAK_MARKERS)

    assert [marker for marker in _NATURAL_MARKERS if marker not in raw] == []
    assert [marker for marker in _LEAK_MARKERS if marker not in raw + canaried] == []
    assert [sentence for sentence in _EVIDENCE_SENTENCES if sentence not in _as_text(raw_records)] == []


@pytest.mark.asyncio
async def test_the_snapshot_consensus_carries_the_stance_value_and_its_round_span():
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    society_memory = AsyncMock(spec=SocietyMemory)
    snapshot = SocietySnapshot(
        round=0,
        entries=[
            {
                "agent": "Bob",
                "round": 1,
                "stance": "POSITIVE",
                "confidence": 0.7,
                "weight": 0.35,
                "summary": "Bob's round one argument.",
                "entities": [],
            }
        ],
    )
    society_memory.read_snapshot.return_value = snapshot
    society_memory.commit_round.return_value = _ok_receipt()
    synth.synthesize.return_value = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    pair = CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    topo.compute_round_pairs.side_effect = lambda *a, **kw: [pair]
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    verdict_synth.asynthesize.return_value = _make_verdict()
    orch = _orch(synth, topo, society_memory, verdict_synth)

    with patch("src.simulation.orchestrator.RoundRunner") as rr_cls:
        rr = MagicMock()
        rr.execute_round = AsyncMock(
            side_effect=lambda **kw: RoundResult(
                round_num=kw["round_num"],
                turns=[_make_turn("1", "Alice"), _make_turn("2", "Bob")],
                pairs=[pair],
            )
        )
        rr_cls.return_value = rr
        await orch.run("q", "ds1", DebateConfig(max_agents=5, max_rounds=2), AsyncMock())

    assert type(snapshot.consensus["stance"]) is str
    assert snapshot.consensus["stance"] == "POSITIVE"
    assert snapshot.consensus["rounds"] == 1
    # The real round-2 snapshot, as the speaker's prompt renders it.
    society = rr.execute_round.call_args_list[1].kwargs["society"]
    text = society.to_prompt("Alice", "Bob")
    assert "Consensus over the last 1 round: POSITIVE holds 100% of the weight." in text
    assert "Stance." not in text


@pytest.mark.asyncio
async def test_final_stances_are_read_from_the_consensus_window():
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)
    society_memory.commit_round.return_value = _ok_receipt()
    synth.synthesize.return_value = [
        _make_profile(1, "Alice"),
        _make_profile(2, "Bob"),
        _make_profile(3, "Carol"),
    ]
    pair = CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    topo.compute_round_pairs.side_effect = lambda *a, **kw: [pair]
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    verdict_synth.asynthesize.return_value = _make_verdict()
    orch = _orch(synth, topo, society_memory, verdict_synth)
    # Carol speaks only in round 1, outside the last-two-round window; an even split keeps the loop running.
    turns_by_round = {
        1: [_make_turn("1", "Alice", "POSITIVE"), _make_turn("2", "Bob", "NEGATIVE"), _make_turn("3", "Carol", "POSITIVE")],
        2: [_make_turn("1", "Alice", "POSITIVE"), _make_turn("2", "Bob", "NEGATIVE")],
        3: [_make_turn("1", "Alice", "POSITIVE"), _make_turn("2", "Bob", "NEGATIVE")],
    }

    with patch("src.simulation.orchestrator.RoundRunner") as rr_cls:
        rr = MagicMock()
        rr.execute_round = AsyncMock(
            side_effect=lambda **kw: RoundResult(
                round_num=kw["round_num"], turns=turns_by_round[kw["round_num"]], pairs=[pair]
            )
        )
        rr_cls.return_value = rr
        result = await orch.run("q", "ds1", DebateConfig(max_agents=5, max_rounds=3), AsyncMock())

    assert result.final_stances == {"Alice": "POSITIVE", "Bob": "NEGATIVE", "Carol": "ABSTAIN"}
