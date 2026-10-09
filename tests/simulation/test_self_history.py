"""The speaker's own prior positions: run-scoped read + prompt block.

Round >= 2, each speaker reads back its OWN committed opinions (the half the
society snapshot deliberately excludes) and renders them as a separate
"YOUR PRIOR POSITIONS" block. Self and the society block stay two distinct
blocks — the society block never contains the speaker's own lines.
"""
import uuid

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.persona.agent import (
    Agent,
    ConfidenceBreakdown,
    DiscoveryType,
    ExpertiseLevel,
    GraphSnapshot,
    PersonaIdentity,
    Stance,
)
from src.simulation.debate_config import DebateConfig
from src.simulation.llm_batch import BatchedLLMRunner
from src.simulation.orchestrator import DebateOrchestrator
from src.simulation.pair_turn import CommPair, DebateVerdict, RoundResult
from src.simulation.profile_synthesizer import ProfileSynthesizer
from src.simulation.society_memory import SocietyMemory, SocietySnapshot
from src.simulation.topology import CommunicationTopology
from src.simulation.verdict import VerdictSynthesizer
from src.simulation.round_runner import _build_user_prompt


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    async def data(self):
        return self._rows


class FakeSession:
    def __init__(self, rows=None):
        self.calls = []
        self._rows = rows or []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def run(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return FakeResult(self._rows)


def _mem_with_rows(rows):
    driver = MagicMock()
    session = FakeSession(rows=rows)
    driver.session.return_value = session
    return SocietyMemory(driver, "db"), session


def _agent(name: str) -> Agent:
    return Agent(
        identity=PersonaIdentity(name=name, archetype="x", communication_style="y"),
        discovery_type=DiscoveryType.GRAPH_DISCOVERY,
    )


@pytest.mark.asyncio
async def test_read_self_history_returns_own_opinions_ordered_by_round():
    # Driver hands them back out of order; the read must order ascending.
    rows = [
        {"round_no": 2, "stance": "NEGATIVE", "summary": "round two"},
        {"round_no": 1, "stance": "POSITIVE", "summary": "round one"},
    ]
    svc, session = _mem_with_rows(rows)

    out = await svc.read_self_history(
        dataset_id="ds1", query_hash="qh1", agent_name="Alice", through_round=3,
    )

    assert out == [
        {"round": 1, "stance": "POSITIVE", "summary": "round one"},
        {"round": 2, "stance": "NEGATIVE", "summary": "round two"},
    ]
    query, params = session.calls[0]
    assert "ORDER BY o.round_no" in query          # ordered at the source
    assert "o.round_no < $through_round" in query  # strictly-prior rounds
    assert params["dataset_id"] == "ds1" and params["query_hash"] == "qh1"
    assert params["agent_name"] == "Alice"


@pytest.mark.asyncio
async def test_read_self_history_truncates_summary_to_budget():
    from src.simulation.society_memory import SELF_HISTORY_SUMMARY_CHARS

    svc, session = _mem_with_rows(
        [{"round_no": 1, "stance": "POSITIVE", "summary": "x " * 300}]
    )

    out = await svc.read_self_history(
        dataset_id="ds1", query_hash="qh1", agent_name="Alice", through_round=2,
    )

    assert len(out[0]["summary"]) <= SELF_HISTORY_SUMMARY_CHARS
    assert session.calls[0][1]["summary_chars"] == SELF_HISTORY_SUMMARY_CHARS


@pytest.mark.asyncio
async def test_read_self_history_empty_when_speaker_has_none():
    svc, _ = _mem_with_rows([])

    out = await svc.read_self_history(
        dataset_id="ds1", query_hash="qh1", agent_name="Newcomer", through_round=1,
    )

    assert out == []


def test_self_entries_default_empty():
    """Round 1 carries no self history — the default is an empty list."""
    assert SocietySnapshot(round=1).self_entries == []


def test_self_prompt_renders_own_positions():
    snap = SocietySnapshot(round=2, self_entries=[
        {"agent": "Alice", "round": 1, "stance": "POSITIVE", "summary": "Alice round one"},
        {"agent": "Bob", "round": 1, "stance": "NEGATIVE", "summary": "Bob round one"},
    ])

    block = snap.self_prompt("Alice")

    assert "YOUR PRIOR POSITIONS (through round 2)" in block
    assert "Alice round one" in block
    assert "Bob round one" not in block  # only the speaker's own lines


def test_self_prompt_omitted_when_speaker_has_none():
    """No prior opinions → no block, no stray header."""
    snap = SocietySnapshot(round=2, self_entries=[
        {"agent": "Bob", "round": 1, "stance": "NEGATIVE", "summary": "Bob round one"},
    ])

    assert snap.self_prompt("Alice") == ""


def test_self_prompt_orders_by_round():
    snap = SocietySnapshot(round=3, self_entries=[
        {"agent": "Alice", "round": 2, "stance": "NEGATIVE", "summary": "later"},
        {"agent": "Alice", "round": 1, "stance": "POSITIVE", "summary": "earlier"},
    ])

    block = snap.self_prompt("Alice")

    assert block.index("earlier") < block.index("later")


def test_user_prompt_shows_own_positions_and_keeps_society_block_self_free():
    """Round >= 2: own lines render in their block; the society block still excludes them."""
    snap = SocietySnapshot(round=2, entries=[
        {"agent": "Alice", "round": 1, "stance": "POSITIVE", "confidence": 0.9,
         "weight": 0.5, "summary": "ALICE SOCIETY LINE"},
        {"agent": "Bob", "round": 1, "stance": "NEGATIVE", "confidence": 0.8,
         "weight": 0.4, "summary": "BOB SOCIETY LINE"},
    ], self_entries=[
        {"agent": "Alice", "round": 1, "stance": "POSITIVE", "summary": "ALICE OWN PRIOR"},
    ])

    prompt = _build_user_prompt(_agent("Alice"), _agent("Bob"), "q", [], society=snap)

    assert "YOUR PRIOR POSITIONS" in prompt
    assert "ALICE OWN PRIOR" in prompt
    society_block = prompt.split("YOUR PRIOR POSITIONS")[0]
    assert "ALICE SOCIETY LINE" not in society_block  # society block still self-free
    assert "BOB SOCIETY LINE" in society_block


def test_user_prompt_hides_prior_positions_in_round_one():
    """Round 1 has no self history: no block at all."""
    snap = SocietySnapshot(round=1, entries=[
        {"agent": "Bob", "round": 1, "stance": "NEGATIVE", "confidence": 0.8,
         "weight": 0.4, "summary": "BOB SOCIETY LINE"},
    ])

    prompt = _build_user_prompt(_agent("Alice"), _agent("Bob"), "q", [], society=snap)

    assert "YOUR PRIOR POSITIONS" not in prompt


def _profile(n: int, name: str) -> Agent:
    return Agent(
        agent_id=uuid.UUID(int=n),
        identity=PersonaIdentity(name=name, archetype="E", communication_style="F"),
        discovery_type=DiscoveryType.INTENT_DRIVEN,
        expertise_level=ExpertiseLevel.TECHNICAL,
        bio="b", detailed_perspective="p", domain_tags=["d"], confidence=0.7,
        confidence_breakdown=ConfidenceBreakdown(
            source_breadth=1, node_density=1, relationship_connectivity=0.5
        ),
        graph_snapshot=GraphSnapshot(dataset_id="ds1"),
    )


def _orchestrator(sm: AsyncMock) -> DebateOrchestrator:
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    synth.synthesize.return_value = [_profile(1, "Alice"), _profile(2, "Bob")]
    topo.compute_round_pairs.return_value = [CommPair(agent_a="Alice", agent_b="Bob")]
    verdict = MagicMock(spec=VerdictSynthesizer)
    verdict.asynthesize.return_value = DebateVerdict(
        overall_stance=Stance.POSITIVE, confidence_score=0.9,
        supporting_entities=[], opposing_entities=[], summary="v",
        cluster_details={}, rounds_executed=1,
    )
    return DebateOrchestrator(
        profile_synthesizer=synth, topology=topo,
        llm_runner=MagicMock(spec=BatchedLLMRunner),
        verdict_synthesizer=verdict, society_memory=sm,
    )


@pytest.mark.asyncio
async def test_run_fetches_self_history_from_round_two_and_passes_it_to_the_runner():
    """The read actually rides the snapshot path the runner consumes — per speaker."""
    sm = AsyncMock(spec=SocietyMemory)
    sm.commit_round.return_value = {"round": 1, "opinions": 2, "edges": 1, "failed": False}
    sm.read_self_history.return_value = [
        {"round": 1, "stance": "POSITIVE", "summary": "prior"}
    ]
    orch = _orchestrator(sm)

    seen: list = []

    with patch("src.simulation.orchestrator.RoundRunner") as rr_cls:
        rr = MagicMock()

        async def execute_round(**kw):
            seen.append(kw.get("society"))
            return RoundResult(round_num=kw["round_num"], turns=[], pairs=[])

        rr.execute_round = AsyncMock(side_effect=execute_round)
        rr_cls.return_value = rr
        await orch.run("q", "ds1", DebateConfig(max_agents=5, max_rounds=2), AsyncMock())

    assert seen[0] is None  # round 1: no snapshot, no self history
    assert [e["agent"] for e in seen[1].self_entries] == ["Alice", "Bob"]
    sm.read_self_history.assert_awaited()  # fetched per speaking agent


@pytest.mark.asyncio
async def test_self_history_read_failure_degrades_to_warning():
    """A failed optional enrichment warns and the run proceeds without the block."""
    sm = AsyncMock(spec=SocietyMemory)
    sm.read_self_history.side_effect = RuntimeError("cypher down")
    orch = _orchestrator(sm)
    warnings: list[str] = []

    snap = await orch._with_self_history(
        None, pairs=[CommPair(agent_a="Alice", agent_b="Bob")],
        dataset_id="ds1", query_hash="qh", round_num=2, warnings=warnings,
    )

    assert snap is None  # nothing to render, no crash
    assert any("self history read failed" in w for w in warnings)

