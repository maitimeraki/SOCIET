"""Tests for DebateOrchestrator."""
import uuid

import pytest
from unittest.mock import ANY, AsyncMock, MagicMock, patch
import asyncio

from src.simulation.orchestrator import DebateOrchestrator, OrchestratedDebateResult
from src.simulation.profile_synthesizer import ProfileSynthesizer
from src.simulation.topology import CommunicationTopology
from src.simulation.pair_turn import ActivationCandidate, CommPair
from src.simulation.llm_batch import BatchedLLMRunner
from src.simulation.verdict import VerdictSynthesizer
from src.simulation.society_memory import SocietyMemory
from src.simulation.debate_config import DebateConfig
from src.simulation.pair_turn import AgentTurn, RoundResult, DebateVerdict
from src.persona.agent import Stance
from src.persona.agent import (
    Agent,
    ConfidenceBreakdown,
    DiscoveryType,
    ExpertiseLevel,
    GraphSnapshot,
    PersonaIdentity,
)
from src.utils.queryIntend import QueryIntent


def _make_profile(agent_id: int, name: str) -> Agent:
    """Canonical Agent stand-in — the debate loop reads it, so every field must resolve."""
    return Agent(
        agent_id=uuid.UUID(int=agent_id),
        identity=PersonaIdentity(name=name, archetype="Expert", communication_style="Formal"),
        discovery_type=DiscoveryType.INTENT_DRIVEN,
        expertise_level=ExpertiseLevel.TECHNICAL,
        bio=f"{name} perspective",
        detailed_perspective=f"{name} perspective",
        domain_tags=[f"{name}_domain"],
        confidence=0.7,
        confidence_breakdown=ConfidenceBreakdown(
            source_breadth=1, node_density=1, relationship_connectivity=0.5
        ),
        graph_snapshot=GraphSnapshot(dataset_id="ds1"),
    )


def _ok_receipt() -> dict:
    """The receipt shape `SocietyMemory.commit_round` returns on success."""
    return {"round": 1, "dataset_id": "ds1", "query_hash": "qhash",
            "opinions": 2, "edges": 1, "failed": False}


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


def _make_turn(agent_id: str, agent_name: str, stance: str = "POSITIVE") -> AgentTurn:
    return AgentTurn(
        agent_id=agent_id,
        agent_name=agent_name,
        content="Test content",
        stance=stance,
        confidence=0.8,
        references=[],
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

    # Step 1: profile_synthesizer called — with the S3 intent, the run's config
    # (so S4 selection can blend against it) and the run's S9 sinks (so the
    # selection decomposition and any S4 degradation land on the result)
    synth.synthesize.assert_awaited_once_with(
        query="test query", dataset_id="ds1", max_agents=5, intent=None, config=config,
        warnings=result.warnings, selection_rows=result.selection_rows, distill=False,
        on_selection=ANY, on_profile=ANY,
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
        patched_rr_instance.execute_round = AsyncMock(return_value=RoundResult(
            round_num=1, turns=[], pairs=[]
        ))
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
async def test_no_profiles_returns_early():
    """If synthesize returns empty, skip all subsequent steps and return empty result."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    society_memory = AsyncMock(spec=SocietyMemory)

    synth.synthesize.return_value = []

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

    assert result.converged is False
    assert "No agents could be synthesized" in result.verdict
    topo.compute_round_pairs.assert_not_called()
    verdict_synth.asynthesize.assert_not_called()
    society_memory.commit_round.assert_not_awaited()
    society_memory.read_snapshot.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_roster_result_keeps_accumulated_warnings():
    """P5-A m1: the early return carries what earlier stages already warned about."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    society_memory = AsyncMock(spec=SocietyMemory)

    async def synthesize(**kwargs):
        kwargs["warnings"].append("S4 selection: degraded to density-only ordering")
        return []

    synth.synthesize.side_effect = synthesize
    orch = _orch(synth, topo, society_memory)

    result = await orch.run("q", "ds1", DebateConfig(max_agents=5, max_rounds=1), AsyncMock())

    assert result.warnings == [
        "S4 selection: degraded to density-only ordering",
        "No relevant entities found for query",
    ]


@pytest.mark.asyncio
async def test_run_threads_the_distill_gate_to_synthesis():
    """S5/D3: the boundary's gate reaches profile synthesis unchanged."""
    orch = _stage_ready_orch(max_rounds=1)

    await orch.run(
        "q", "ds1", DebateConfig(max_agents=5, max_rounds=1), AsyncMock(), distill=True,
    )

    assert orch._profile_synthesizer.synthesize.await_args.kwargs["distill"] is True


@pytest.mark.asyncio
async def test_convergence_check_breaks_loop():
    """Loop breaks early when _check_convergence returns True."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    society_memory = AsyncMock(spec=SocietyMemory)

    profiles = [_make_profile(1, "Alice")]
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
async def test_convergence_false_when_insufficient_rounds():
    """_check_convergence returns False when fewer than 2 rounds."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    society_memory = AsyncMock(spec=SocietyMemory)

    profiles = [_make_profile(1, "Alice")]
    synth.synthesize.return_value = profiles
    topo.compute_round_pairs.return_value = []
    verdict_synth.asynthesize.return_value = _make_verdict()
    llm_runner.gather = MagicMock(return_value=_AsyncEmptyIter())

    orchestrator = DebateOrchestrator(
        profile_synthesizer=synth,
        topology=topo,
        llm_runner=llm_runner,
        verdict_synthesizer=verdict_synth,
        society_memory=society_memory,
    )

    ws_broadcast = AsyncMock()
    config = DebateConfig(max_agents=5, max_rounds=1)

    result = await orchestrator.run("test query", "ds1", config, ws_broadcast)

    assert result.converged is False


@pytest.mark.asyncio
async def test_check_convergence_domimant_stance_threshold():
    """_check_convergence returns True when dominant stance >= 80% of turns."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    society_memory = AsyncMock(spec=SocietyMemory)

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
    assert orchestrator._check_convergence([r1]) is False  # < 2 rounds
    assert orchestrator._check_convergence([r1, r2]) is True  # 100% dominant


@pytest.mark.asyncio
async def test_commit_failure_degrades_to_warning():
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    society_memory = AsyncMock(spec=SocietyMemory)
    synth.synthesize.return_value = [_make_profile(1, "Alice")]
    topo.compute_round_pairs.side_effect = lambda *a, **kw: [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    verdict_synth.asynthesize.return_value = _make_verdict()
    society_memory.commit_round.side_effect = RuntimeError("db down")
    llm_runner.gather = MagicMock(side_effect=lambda *a, **kw: _AsyncEmptyIter())

    orchestrator = DebateOrchestrator(
        profile_synthesizer=synth, topology=topo, llm_runner=llm_runner,
        verdict_synthesizer=verdict_synth, society_memory=society_memory,
    )
    result = await orchestrator.run("q", "ds1", DebateConfig(max_agents=5, max_rounds=1), AsyncMock())
    assert any("commit failed" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_commit_failure_first_round_does_not_abort_loop():
    """A commit failure on round 1 degrades to a warning; round 2 still runs and commits."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    society_memory = AsyncMock(spec=SocietyMemory)
    synth.synthesize.return_value = [_make_profile(1, "Alice")]
    topo.compute_round_pairs.side_effect = lambda *a, **kw: [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    verdict_synth.asynthesize.return_value = _make_verdict()
    llm_runner.gather = MagicMock(side_effect=lambda *a, **kw: _AsyncEmptyIter())
    # Round 1 blows up, round 2 commits fine — the loop must survive the first.
    society_memory.commit_round.side_effect = [RuntimeError("db down"), _ok_receipt()]

    orchestrator = DebateOrchestrator(
        profile_synthesizer=synth, topology=topo, llm_runner=llm_runner,
        verdict_synthesizer=verdict_synth, society_memory=society_memory,
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
    synth, topo, llm_runner, verdict_synth = (AsyncMock(spec=ProfileSynthesizer),
                                              AsyncMock(spec=CommunicationTopology),
                                              MagicMock(spec=BatchedLLMRunner),
                                              MagicMock(spec=VerdictSynthesizer))
    synth.synthesize.return_value = [_make_profile(1, "Alice")]
    topo.compute_round_pairs.side_effect = lambda *a, **kw: [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    verdict_synth.asynthesize.return_value = _make_verdict()
    llm_runner.gather = MagicMock(side_effect=lambda *a, **kw: _AsyncEmptyIter())
    society_memory = AsyncMock(spec=SocietyMemory)
    orchestrator = DebateOrchestrator(
        profile_synthesizer=synth, topology=topo, llm_runner=llm_runner,
        verdict_synthesizer=verdict_synth, society_memory=society_memory,
    )
    # 100% dominant on last 2 rounds → converged with low threshold...
    t = _make_turn("1", "Alice", "POSITIVE")
    r1 = RoundResult(round_num=1, turns=[t], pairs=[])
    r2 = RoundResult(round_num=2, turns=[t], pairs=[])
    assert orchestrator._check_convergence([r1, r2], None, config=DebateConfig(convergence_threshold=0.8)) is True
    # ...and a 50%-dominant mix is rejected at 0.8 but accepted at 0.4
    n = _make_turn("1", "Alice", "NEGATIVE")
    r2b = RoundResult(round_num=2, turns=[t, n], pairs=[])
    assert orchestrator._check_convergence([r1, r2b], None, config=DebateConfig(convergence_threshold=0.8)) is False
    assert orchestrator._check_convergence([r1, r2b], None, config=DebateConfig(convergence_threshold=0.4)) is True


def _orch(synth, topo, society_memory, verdict_synth=None, llm_runner=None):
    if verdict_synth is None:
        verdict_synth = MagicMock(spec=VerdictSynthesizer)
        # run() awaits asynthesize; an unconfigured AsyncMock cannot yield verdict fields.
        verdict_synth.asynthesize.return_value = _make_verdict()
    return DebateOrchestrator(
        profile_synthesizer=synth, topology=topo,
        llm_runner=llm_runner or MagicMock(spec=BatchedLLMRunner),
        verdict_synthesizer=verdict_synth,
        society_memory=society_memory,
    )


@pytest.mark.asyncio
async def test_activation_pulls_in_candidates_after_commit():
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    society_memory = AsyncMock(spec=SocietyMemory)
    # Explicit successful receipt: an unset AsyncMock return degrades to the commit-failed branch.
    society_memory.commit_round.return_value = _ok_receipt()
    synth.synthesize.return_value = [_make_profile(1, "Alice")]
    new_profile = _make_profile(2, "Carl")
    synth.synthesize_from_names = AsyncMock(return_value=[new_profile])
    topo.compute_round_pairs.side_effect = lambda *a, **kw: [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    topo.find_activation_candidates = AsyncMock(return_value=[
        ActivationCandidate(agent_name="Carl", shared_entities=["carbon"], reason="mentioned entity in the debate")
    ])
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
    society_memory.commit_round.return_value = _ok_receipt()
    synth.synthesize.return_value = [_make_profile(1, "Alice")]
    synth.synthesize_from_names = AsyncMock(return_value=[])
    topo.compute_round_pairs.side_effect = lambda *a, **kw: [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    topo.find_activation_candidates = AsyncMock(return_value=[
        ActivationCandidate(agent_name="Carl", shared_entities=["carbon"], reason="mentioned entity in the debate")
    ])
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


@pytest.mark.asyncio
async def test_activation_disabled_by_config():
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    society_memory = AsyncMock(spec=SocietyMemory)
    # Explicit successful receipt: an unset AsyncMock return degrades to the commit-failed branch.
    society_memory.commit_round.return_value = _ok_receipt()
    synth.synthesize.return_value = [_make_profile(1, "Alice")]
    synth.synthesize_from_names = AsyncMock(return_value=[])
    topo.compute_round_pairs.side_effect = lambda *a, **kw: [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    topo.find_activation_candidates = AsyncMock(return_value=[
        ActivationCandidate(agent_name="Carl")
    ])
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
async def test_run_threads_intent_to_round_runner_and_result():
    """S3: the run's intent reaches the prompt builder and is exposed on the result."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.commit_round.return_value = _ok_receipt()
    synth.synthesize.return_value = [_make_profile(1, "Alice")]
    topo.compute_round_pairs.return_value = [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    llm_runner.gather = MagicMock(side_effect=lambda *a, **kw: _AsyncEmptyIter())
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    verdict_synth.asynthesize.return_value = _make_verdict()
    intent = QueryIntent(
        direct_keywords=["carbon"], latent_sectors=[], search_perspectives=[],
        core_question="Tax carbon?", stance_axis="Support = tax it.",
    )

    orch = _orch(synth, topo, society_memory, verdict_synth, llm_runner)
    with patch("src.simulation.orchestrator.RoundRunner") as patched_rr_class:
        patched_rr_instance = MagicMock()
        patched_rr_instance.execute_round = AsyncMock(
            return_value=RoundResult(round_num=1, turns=[], pairs=[])
        )
        patched_rr_class.return_value = patched_rr_instance

        result = await orch.run(
            "q", "ds1", DebateConfig(max_agents=5, max_rounds=1), AsyncMock(), intent=intent
        )

        assert patched_rr_class.call_args.kwargs["intent"] is intent
    assert result.intent is intent


@pytest.mark.asyncio
async def test_run_without_intent_exposes_none():
    """Backward compatibility: older callers pass no intent and the run still completes."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.commit_round.return_value = _ok_receipt()
    synth.synthesize.return_value = [_make_profile(1, "Alice")]
    topo.compute_round_pairs.return_value = [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    llm_runner.gather = MagicMock(side_effect=lambda *a, **kw: _AsyncEmptyIter())
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    verdict_synth.asynthesize.return_value = _make_verdict()

    orch = _orch(synth, topo, society_memory, verdict_synth, llm_runner)
    result = await orch.run("q", "ds1", DebateConfig(max_agents=5, max_rounds=1), AsyncMock())
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
    society_memory.commit_round.return_value = _ok_receipt()
    synth.synthesize.return_value = profiles if profiles is not None else [_make_profile(1, "Alice")]
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
    society_memory.commit_round.return_value = _ok_receipt()
    synth.synthesize.return_value = [_make_profile(1, "Alice")]
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
        rr_instance.execute_round = AsyncMock(side_effect=lambda **kw: RoundResult(
            round_num=kw["round_num"], turns=[_make_turn("1", "Alice")], pairs=[pair],
        ))
        rr_cls.return_value = rr_instance

        result = await orch.run(
            "q", "ds1", DebateConfig(max_agents=5, max_rounds=3), AsyncMock(), on_stage=emit
        )

    assert [(e["stage"], e.get("round")) for e in events] == [
        ("intake", None), ("selection", None), ("synthesis", None),
        ("round", 1), ("round", 2), ("round", 3),
        ("convergence", None), ("verdict", None),
    ]
    assert all(e["type"] == "stage" for e in events)
    assert [e["index"] for e in events] == list(range(len(events)))
    assert events[0]["query"] == "q"
    assert events[2]["agents"] == 1
    # the round event reports that round's own execution
    assert (events[3]["round"], events[3]["pairs"], events[3]["turns"]) == (1, 1, 1)
    assert events[4]["round"] == 2 and events[5]["round"] == 3
    assert events[-2]["converged"] is result.converged
    assert events[-2]["rounds_executed"] == result.rounds_executed == 3


@pytest.mark.asyncio
async def test_stage_events_stop_at_verdict_when_nothing_is_synthesized():
    """No roster → no round/convergence event, but the run still says how it ended."""
    orch = _stage_ready_orch(profiles=[])
    events, emit = _stage_spy()

    result = await orch.run(
        "q", "ds1", DebateConfig(max_agents=5, max_rounds=3), AsyncMock(), on_stage=emit
    )

    assert [e["stage"] for e in events] == ["intake", "selection", "synthesis", "verdict"]
    assert events[2]["agents"] == 0
    assert events[3]["converged"] is False and events[3]["rounds_executed"] == 0
    assert result.rounds_executed == 0


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
        "q", "ds1", DebateConfig(max_agents=5, max_rounds=1), AsyncMock(),
        on_stage=exploding_emitter,
    )
    assert result.rounds_executed == 1
    assert result.verdict == "Test verdict."


"""P5: the run streams the S4 selection, each built profile and the round's weights."""


def _orchestrator_with(synth, topo, llm_runner, verdict_synth, society_memory):
    return DebateOrchestrator(
        profile_synthesizer=synth,
        topology=topo,
        llm_runner=llm_runner,
        verdict_synthesizer=verdict_synth,
        society_memory=society_memory,
    )


@pytest.mark.asyncio
async def test_selection_and_agent_events_are_broadcast():
    """S4/S5 progression is visible: selection once, then one agent event per profile, in order."""
    from src.simulation.relevance_matrix import SelectionRow

    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    society_memory = AsyncMock(spec=SocietyMemory)

    profiles = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    row = SelectionRow(name="Alice", semantic=0.8, density=0.6, blended=0.72)

    async def fake_synthesize(**kwargs):
        await kwargs["on_selection"]([row])
        for index, profile in enumerate(profiles, start=1):
            await kwargs["on_profile"](profile, index, len(profiles))
        return profiles

    synth.synthesize.side_effect = fake_synthesize
    topo.compute_round_pairs.return_value = []
    verdict_synth.asynthesize.return_value = _make_verdict()

    orchestrator = _orchestrator_with(synth, topo, llm_runner, verdict_synth, society_memory)
    ws_calls = []

    async def fake_ws(msg):
        ws_calls.append(msg)

    await orchestrator.run("test query", "ds1", DebateConfig(max_agents=5, max_rounds=1), fake_ws)

    types = [m["type"] for m in ws_calls]
    assert types.index("selection") < types.index("agent")
    agents = [m for m in ws_calls if m["type"] == "agent"]
    assert [m["index"] for m in agents] == [1, 2]
    assert all(m["total"] == 2 for m in agents)
    assert agents[0]["profile"]["identity"]["name"] == "Alice"


@pytest.mark.asyncio
async def test_round_events_carry_consensus_weights():
    """Each round exposes the per-stance weight share — the convergence tape's input."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    society_memory = AsyncMock(spec=SocietyMemory)

    profiles = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    synth.synthesize.return_value = profiles
    topo.compute_round_pairs.return_value = [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    verdict_synth.asynthesize.return_value = _make_verdict()
    verdict_synth._calibrate_cior.return_value = {
        Stance.POSITIVE: 60.0, Stance.NEGATIVE: 40.0, Stance.NEUTRAL: 0.0, Stance.AMBIVALENT: 0.0,
    }
    society_memory.commit_round.return_value = _ok_receipt()

    rounds = [
        RoundResult(
            round_num=1,
            pairs=[CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)],
            turns=[_make_turn("id-1", "Alice", "POSITIVE"), _make_turn("id-2", "Bob", "NEGATIVE")],
        )
    ]

    with patch("src.simulation.orchestrator.RoundRunner") as patched_rr_class:
        instance = MagicMock()
        instance.execute_round = AsyncMock(side_effect=rounds)
        patched_rr_class.return_value = instance

        orchestrator = _orchestrator_with(synth, topo, llm_runner, verdict_synth, society_memory)
        ws_calls = []

        async def fake_ws(msg):
            ws_calls.append(msg)

        await orchestrator.run("test query", "ds1", DebateConfig(max_agents=5, max_rounds=1), fake_ws)

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

    profiles = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    synth.synthesize.return_value = profiles
    topo.compute_round_pairs.return_value = [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    verdict_synth.asynthesize.return_value = _make_verdict()
    society_memory.commit_round.return_value = {"round": 1, "opinions": 0, "edges": 0, "failed": True, "error": "neo4j down"}

    rounds = [
        RoundResult(
            round_num=1,
            pairs=[CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)],
            turns=[_make_turn("id-1", "Alice")],
        )
    ]

    with patch("src.simulation.orchestrator.RoundRunner") as patched_rr_class:
        instance = MagicMock()
        instance.execute_round = AsyncMock(side_effect=rounds)
        patched_rr_class.return_value = instance

        orchestrator = _orchestrator_with(synth, topo, llm_runner, verdict_synth, society_memory)
        ws_calls = []

        async def fake_ws(msg):
            ws_calls.append(msg)

        result = await orchestrator.run("test query", "ds1", DebateConfig(max_agents=5, max_rounds=1), fake_ws)

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

    profiles = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    synth.synthesize.return_value = profiles
    topo.compute_round_pairs.return_value = [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    verdict_synth.asynthesize.return_value = _make_verdict()
    verdict_synth._calibrate_cior.return_value = {
        Stance.POSITIVE: 60.0, Stance.NEGATIVE: 40.0, Stance.NEUTRAL: 0.0, Stance.AMBIVALENT: 0.0,
    }
    society_memory.commit_round.return_value = _ok_receipt()

    rounds = [
        RoundResult(
            round_num=1,
            pairs=[CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)],
            turns=[_make_turn("id-1", "Alice", "POSITIVE"), _make_turn("id-2", "Bob", "NEGATIVE")],
        )
    ]

    with patch("src.simulation.orchestrator.RoundRunner") as patched_rr_class:
        instance = MagicMock()
        instance.execute_round = AsyncMock(side_effect=rounds)
        patched_rr_class.return_value = instance

        orchestrator = _orchestrator_with(synth, topo, llm_runner, verdict_synth, society_memory)
        ws_calls = []

        async def fake_ws(msg):
            ws_calls.append(msg)

        await orchestrator.run(
            "test query", "ds1", DebateConfig(max_agents=5, max_rounds=1), fake_ws, on_stage=fake_ws,
        )

    stage_event = next(m for m in ws_calls if m["type"] == "stage" and m["stage"] == "convergence")
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

    synth.synthesize.return_value = [_make_profile(1, "Alice")]
    topo.compute_round_pairs.return_value = []
    verdict = _make_verdict()
    verdict.cluster_details = {
        Stance.POSITIVE: ClusterSummary(
            stance=Stance.POSITIVE, count=2, total_weight=0.6,
            avg_confidence=0.7, avg_conviction=0.6, agents=["Alice"],
        )
    }
    verdict.supporting_entities = ["Steel tariffs"]
    verdict.opposing_entities = ["Entry cost"]
    verdict_synth.asynthesize.return_value = verdict

    orchestrator = _orchestrator_with(synth, topo, llm_runner, verdict_synth, society_memory)
    ws_calls = []

    async def fake_ws(msg):
        ws_calls.append(msg)

    result = await orchestrator.run("test query", "ds1", DebateConfig(max_agents=5, max_rounds=1), fake_ws)

    assert result.confidence_score == 0.9
    assert result.cluster_details["POSITIVE"]["count"] == 2
    assert result.cluster_details["POSITIVE"]["stance"] == "POSITIVE"
    assert result.supporting_entities == ["Steel tariffs"]
    assert result.opposing_entities == ["Entry cost"]
