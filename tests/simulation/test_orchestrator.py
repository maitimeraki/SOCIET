"""Tests for DebateOrchestrator."""
import uuid

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
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
from src.simulation.agent_node import Stance
from src.persona.agent import (
    Agent,
    ConfidenceBreakdown,
    DiscoveryType,
    ExpertiseLevel,
    GraphSnapshot,
    PersonaIdentity,
)


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

    # Step 1: profile_synthesizer called
    synth.synthesize.assert_awaited_once_with(
        query="test query", dataset_id="ds1", max_agents=5
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
    verdict_synth.synthesize.return_value = _make_verdict()
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
    verdict_synth.synthesize.return_value = _make_verdict()
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
    verdict_synth.synthesize.return_value = _make_verdict()
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
    verdict_synth.synthesize.return_value = _make_verdict()

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
    verdict_synth.synthesize.return_value = _make_verdict()
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
    verdict_synth.synthesize.return_value = _make_verdict()
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
    verdict_synth.synthesize.return_value = _make_verdict()
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
    return DebateOrchestrator(
        profile_synthesizer=synth, topology=topo,
        llm_runner=llm_runner or MagicMock(spec=BatchedLLMRunner),
        verdict_synthesizer=verdict_synth or MagicMock(spec=VerdictSynthesizer),
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
    verdict_synth.synthesize.return_value = _make_verdict()

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
    verdict_synth.synthesize.return_value = _make_verdict()

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
