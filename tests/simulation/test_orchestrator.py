"""Tests for DebateOrchestrator."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from src.simulation.orchestrator import DebateOrchestrator, OrchestratedDebateResult
from src.simulation.profile_synthesizer import ProfileSynthesizer
from src.simulation.topology import CommunicationTopology
from src.simulation.pair_turn import CommPair
from src.simulation.llm_batch import BatchedLLMRunner
from src.simulation.verdict import VerdictSynthesizer
from src.simulation.writeback import WriteBackService
from src.simulation.debate_config import DebateConfig
from src.simulation.pair_turn import AgentTurn, RoundResult, DebateVerdict
from src.simulation.agent_node import Stance
from src.persona.models_persona import AgentProfile, PersonaIdentity


def _make_profile(agent_id: int, name: str) -> AgentProfile:
    identity = MagicMock(spec=PersonaIdentity)
    identity.name = name
    profile = MagicMock(spec=AgentProfile)
    profile.agent_id = agent_id
    profile.identity = identity
    return profile


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
    """Verify all 5 steps execute: profiles → topology → round → verdict → writeback."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    writeback = AsyncMock(spec=WriteBackService)

    profiles = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    synth.synthesize.return_value = profiles
    topo.compute_round_pairs.return_value = [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    verdict_synth.synthesize.return_value = _make_verdict()
    writeback.persist_round_turns.return_value = None
    llm_runner.gather = MagicMock(return_value=_AsyncEmptyIter())

    orchestrator = DebateOrchestrator(
        profile_synthesizer=synth,
        topology=topo,
        llm_runner=llm_runner,
        verdict_synthesizer=verdict_synth,
        writeback=writeback,
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
    verdict_synth.synthesize.assert_called_once()

    # Step 4: writeback called once
    writeback.persist_round_turns.assert_awaited_once()

    assert isinstance(result, OrchestratedDebateResult)
    assert result.verdict == "Test verdict."
    assert result.rounds_executed == 3


@pytest.mark.asyncio
async def test_ws_broadcast_passed_to_round_runner():
    """ws_broadcast is passed through to RoundRunner constructor."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    writeback = AsyncMock(spec=WriteBackService)

    profiles = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    synth.synthesize.return_value = profiles
    topo.compute_round_pairs.return_value = [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    verdict_synth.synthesize.return_value = _make_verdict()
    writeback.persist_round_turns.return_value = None
    llm_runner.gather = MagicMock(return_value=_AsyncEmptyIter())

    orchestrator = DebateOrchestrator(
        profile_synthesizer=synth,
        topology=topo,
        llm_runner=llm_runner,
        verdict_synthesizer=verdict_synth,
        writeback=writeback,
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

        await orchestrator.run("test query", "ds1", config, fake_ws)

        # Verify RoundRunner was constructed with the ws_broadcast
        patched_rr_class.assert_called_once()
        call_kwargs = patched_rr_class.call_args.kwargs
        assert "ws_broadcast" in call_kwargs
        assert call_kwargs["ws_broadcast"] is fake_ws


@pytest.mark.asyncio
async def test_no_profiles_returns_early():
    """If synthesize returns empty, skip all subsequent steps and return empty result."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    writeback = AsyncMock(spec=WriteBackService)

    synth.synthesize.return_value = []

    orchestrator = DebateOrchestrator(
        profile_synthesizer=synth,
        topology=topo,
        llm_runner=llm_runner,
        verdict_synthesizer=verdict_synth,
        writeback=writeback,
    )

    ws_broadcast = AsyncMock()
    config = DebateConfig(max_agents=5, max_rounds=3)

    result = await orchestrator.run("test query", "ds1", config, ws_broadcast)

    assert result.converged is False
    assert "No agents could be synthesized" in result.verdict
    topo.compute_round_pairs.assert_not_called()
    verdict_synth.synthesize.assert_not_called()
    writeback.persist_round_turns.assert_not_called()


@pytest.mark.asyncio
async def test_convergence_check_breaks_loop():
    """Loop breaks early when _check_convergence returns True."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    writeback = AsyncMock(spec=WriteBackService)

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
    writeback.persist_round_turns.return_value = None
    # Fresh iterator per call so each round gets an empty async iterator
    llm_runner.gather = MagicMock(side_effect=lambda *a, **kw: _AsyncEmptyIter())

    orchestrator = DebateOrchestrator(
        profile_synthesizer=synth,
        topology=topo,
        llm_runner=llm_runner,
        verdict_synthesizer=verdict_synth,
        writeback=writeback,
    )

    # Override _check_convergence with a sync function (same signature as the real method)
    def fake_convergence(rounds):
        return len(rounds) >= 2

    orchestrator._check_convergence = fake_convergence

    ws_broadcast = AsyncMock()
    config = DebateConfig(max_agents=5, max_rounds=5)

    await orchestrator.run("test query", "ds1", config, ws_broadcast)

    # Should stop at 2 rounds instead of max_rounds=5
    assert topo.compute_round_pairs.call_count == 2


@pytest.mark.asyncio
async def test_convergence_false_when_insufficient_rounds():
    """_check_convergence returns False when fewer than 2 rounds."""
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    llm_runner = MagicMock(spec=BatchedLLMRunner)
    verdict_synth = MagicMock(spec=VerdictSynthesizer)
    writeback = AsyncMock(spec=WriteBackService)

    profiles = [_make_profile(1, "Alice")]
    synth.synthesize.return_value = profiles
    topo.compute_round_pairs.return_value = []
    verdict_synth.synthesize.return_value = _make_verdict()
    writeback.persist_round_turns.return_value = None
    llm_runner.gather = MagicMock(return_value=_AsyncEmptyIter())

    orchestrator = DebateOrchestrator(
        profile_synthesizer=synth,
        topology=topo,
        llm_runner=llm_runner,
        verdict_synthesizer=verdict_synth,
        writeback=writeback,
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
    writeback = AsyncMock(spec=WriteBackService)

    profiles = [_make_profile(1, "Alice"), _make_profile(2, "Bob")]
    synth.synthesize.return_value = profiles
    topo.compute_round_pairs.return_value = [
        CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
    ]
    verdict_synth.synthesize.return_value = _make_verdict()
    writeback.persist_round_turns.return_value = None

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
        writeback=writeback,
    )

    # Test _check_convergence directly
    assert orchestrator._check_convergence([r1]) is False  # < 2 rounds
    assert orchestrator._check_convergence([r1, r2]) is True  # 100% dominant
