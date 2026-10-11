"""Snapshot read fidelity: config-controlled render, per-speaker reads, run-scoped markers.

Covers the three read-loop gaps fixed together: `snapshot_top_k` must control how
many society opinions render, a dominant speaker's own lines must not crowd others
out of the pool, and a `[directly connected to you]` marker must only reflect a
connection valid for this debate (this dataset + this query_hash).
"""
import os
import uuid

import pytest
import pytest_asyncio
from dotenv import load_dotenv
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
from src.simulation.round_runner import RoundRunner, _build_user_prompt
from src.simulation.society_memory import SocietyMemory, SocietySnapshot
from src.simulation.topology import CommunicationTopology
from src.simulation.verdict import VerdictSynthesizer
from src.persona.repository import PersonaRepository

load_dotenv()


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    async def data(self):
        return self._rows


class FakeSession:
    """Honours the speaker-exclusion clause so the per-speaker read is tested behaviourally."""

    def __init__(self, rows=None):
        self.calls = []
        self._rows = rows or []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def run(self, query, **kwargs):
        self.calls.append((query, kwargs))
        if "OPPOSES|SUPPORTS" in query:
            return FakeResult([])  # neighbor read yields no connections unless stubbed
        rows = self._rows
        if "o.agent_name <> $speaker" in query:
            rows = [r for r in rows if r.get("agent") != kwargs.get("speaker")]
        return FakeResult(rows)


def _mem(rows):
    driver = MagicMock()
    session = FakeSession(rows=rows)
    driver.session.return_value = session
    return SocietyMemory(driver, "db"), session


def _opinion(agent, weight, summary, round_no=1, entities=None):
    return {"agent": agent, "round_no": round_no, "stance": "POSITIVE",
            "confidence": 0.8, "weight": weight, "summary": summary,
            "entities": entities or []}


def _entry(agent, weight, summary, round_no=1):
    return {"agent": agent, "round": round_no, "stance": "POSITIVE",
            "confidence": 0.8, "weight": weight, "summary": summary}


def _agent(name: str) -> Agent:
    return Agent(
        agent_id=uuid.uuid4(),
        identity=PersonaIdentity(name=name, archetype="Expert", communication_style="Formal"),
        discovery_type=DiscoveryType.INTENT_DRIVEN,
        expertise_level=ExpertiseLevel.TECHNICAL,
        bio=f"{name} bio", detailed_perspective=f"{name} perspective",
        domain_tags=["d"], confidence=0.7,
        confidence_breakdown=ConfidenceBreakdown(
            source_breadth=1, node_density=1, relationship_connectivity=0.5
        ),
        graph_snapshot=GraphSnapshot(dataset_id="ds1"),
    )


def _society_block_lines(prompt: str) -> list[str]:
    block = prompt.split("SOCIETY STATE", 1)[-1]
    block = block.split("YOUR PRIOR POSITIONS")[0]
    return [ln for ln in block.splitlines() if ln.startswith("- ")]


# ------------------------------------------------------------------
# Step 1/2 — the configured count controls the render at the real call site
# ------------------------------------------------------------------

def test_user_prompt_renders_configured_snapshot_count():
    """The society block is capped by the count the caller passes, not a fixed 6."""
    entries = [_entry(f"Agent{i}", 1.0 - i * 0.01, f"line {i}") for i in range(8)]
    snap = SocietySnapshot(round=2, entries=entries)

    prompt = _build_user_prompt(
        _agent("Alice"), _agent("Bob"), "q", [], society=snap, max_opinions=3
    )

    rendered = _society_block_lines(prompt)
    assert len(rendered) == 3
    assert "line 0" in prompt and "line 1" in prompt and "line 2" in prompt
    assert "line 3" not in prompt


@pytest.mark.asyncio
async def test_execute_round_threads_max_opinions_into_every_prompt():
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(return_value="ok")
    rr = RoundRunner(BatchedLLMRunner(mock_llm))
    entries = [_entry(f"Other{i}", 1.0 - i * 0.01, f"line {i}") for i in range(8)]
    snap = SocietySnapshot(round=2, entries=entries)

    await rr.execute_round(
        [_agent("Alice"), _agent("Bob")],
        [CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[])],
        round_num=2, query="Q?", history=[], society=snap, max_opinions=2,
    )

    assert len(mock_llm.generate.call_args_list) == 2
    for c in mock_llm.generate.call_args_list:
        assert len(_society_block_lines(c.kwargs["user_prompt"])) == 2


def _orchestrator(sm) -> DebateOrchestrator:
    synth = AsyncMock(spec=ProfileSynthesizer)
    topo = AsyncMock(spec=CommunicationTopology)
    synth.synthesize.return_value = [_agent("Alice"), _agent("Bob")]
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
async def test_orchestrator_threads_config_snapshot_top_k_to_the_runner():
    """The configured count actually flows from config.snapshot_top_k into the runner."""
    sm = AsyncMock(spec=SocietyMemory)
    sm.commit_round.return_value = {"round": 1, "opinions": 2, "edges": 1, "failed": False}
    orch = _orchestrator(sm)

    seen: list = []

    with patch("src.simulation.orchestrator.RoundRunner") as rr_cls:
        rr = MagicMock()

        async def execute_round(**kw):
            seen.append(kw.get("max_opinions"))
            return RoundResult(round_num=kw["round_num"], turns=[], pairs=[])

        rr.execute_round = AsyncMock(side_effect=execute_round)
        rr_cls.return_value = rr
        await orch.run("q", "ds1", DebateConfig(max_agents=5, max_rounds=2, snapshot_top_k=7), AsyncMock())

    assert seen and all(value == 7 for value in seen)


# ------------------------------------------------------------------
# Step 3/4 — a dominant speaker's own lines cannot crowd out others
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_snapshot_excludes_the_speaker_so_others_still_render():
    """The speaker's many high-weight own opinions must not displace a low-weight other."""
    rows = [_opinion("Alice", 0.9, f"alice {i}") for i in range(20)]
    rows.append(_opinion("Bob", 0.05, "bob line"))
    svc, session = _mem(rows)

    snap = await svc.read_snapshot(
        "ds1", "qh1", through_round=1, top_k=8, speakers=["Alice"]
    )

    op_q, params = session.calls[0]
    assert "o.agent_name <> $speaker" in op_q   # the read excludes the speaker
    assert params["speaker"] == "Alice"
    assert [e["agent"] for e in snap.entries_by_speaker["Alice"]] == ["Bob"]
    assert "bob line" in snap.to_prompt(speaker="Alice", opponent="Bob")


# ------------------------------------------------------------------
# Step 5/6 — the connection marker is scoped to this run
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_neighbor_read_scopes_opposes_to_this_run():
    """An OPPOSES/SUPPORTS edge only marks a neighbour when the pair is connected in this run."""
    svc, session = _mem([])

    await svc.read_snapshot("ds1", "qh1", through_round=2, top_k=8)

    nq, params = next((q, kw) for (q, kw) in session.calls if "OPPOSES|SUPPORTS" in q)
    # The run-scoped REACTED_TO arm stays...
    assert "type(r) = 'REACTED_TO' AND r.query_hash = $query_hash" in nq
    # ...and OPPOSES/SUPPORTS only counts when corroborated by a shared graph entity
    # or a same-run REACTED_TO edge — no bare static edge marks a neighbour.
    assert "NOT e:Chunk AND NOT e:Persona" in nq
    assert "MATCH (p)-[x:REACTED_TO]-(q) WHERE x.query_hash = $query_hash" in nq
    assert params["query_hash"] == "qh1"


# ------------------------------------------------------------------
# Step 7 — degradation: empty snapshot, no connections
# ------------------------------------------------------------------

def test_empty_snapshot_renders_empty_string():
    assert SocietySnapshot(round=1).to_prompt(speaker="Alice", opponent="Bob") == ""


def test_no_connections_render_valid_block_without_markers():
    snap = SocietySnapshot(
        round=2,
        entries=[_entry("Bob", 0.5, "bob line")],
        neighbor_map={},
    )

    prompt = snap.to_prompt(speaker="Alice", opponent="Bob")

    assert "SOCIETY STATE" in prompt
    assert "bob line" in prompt
    assert "[directly connected to you]" not in prompt


def test_connected_neighbour_renders_marker():
    snap = SocietySnapshot(
        round=2,
        entries=[_entry("Bob", 0.5, "bob line")],
        neighbor_map={"Alice": ["Bob"]},
    )
    assert "[directly connected to you]" in snap.to_prompt(speaker="Alice", opponent="Bob")


# ------------------------------------------------------------------
# Step 5/6 — live behavioural proof against the real graph
# ------------------------------------------------------------------

@pytest_asyncio.fixture
async def live_memory():
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    pwd = os.getenv("NEO4J_PASSWORD", "password")
    db = os.getenv("NEO4J_DATABASE", "neo4j")

    repo = PersonaRepository(
        neo4j_uri=uri, neo4j_user=user, neo4j_password=pwd, neo4j_database=db,
    )
    try:
        async with repo._driver.session(database=db) as session:
            await session.run("RETURN 1")
    except Exception as exc:
        await repo.close()
        pytest.skip(f"Neo4j not available at {uri}: {exc}")

    yield SocietyMemory(repo._driver, db), repo._driver, db
    await repo.close()


@pytest.mark.asyncio
async def test_marker_is_scoped_to_the_current_run_on_the_live_graph(live_memory):
    """The central Step 5 claim, decided by the real query rather than a substring.

    A static OPPOSES edge plus a REACTED_TO under a *different* query_hash must NOT
    mark the current run; the same-run REACTED_TO arm must still mark it.
    """
    memory, driver, db = live_memory
    ds = f"itest-snapshot-{uuid.uuid4().hex[:10]}"
    q_new, q_old = "qh-new", "qh-old"

    try:
        async with driver.session(database=db) as session:
            await session.run(
                """
                MERGE (a:Persona {name: 'itest-A', dataset_id: $ds})
                MERGE (b:Persona {name: 'itest-B', dataset_id: $ds})
                MERGE (c:Persona {name: 'itest-C', dataset_id: $ds})
                MERGE (d:Persona {name: 'itest-D', dataset_id: $ds})
                // A-B: a static OPPOSES edge whose only debate edge is in another run.
                MERGE (a)-[:OPPOSES]->(b)
                MERGE (a)-[:REACTED_TO {dataset_id: $ds, query_hash: $q_old, round_no: 1}]->(b)
                // C-D: a same-run REACTED_TO edge and nothing else.
                MERGE (c)-[:REACTED_TO {dataset_id: $ds, query_hash: $q_new, round_no: 1}]->(d)
                WITH b, d
                MERGE (ob:Opinion {dataset_id: $ds, query_hash: $q_new, round_no: 1, agent_name: 'itest-B'})
                SET ob.text = 'bob opinion', ob.stance = 'NEGATIVE', ob.confidence = 0.8,
                    ob.weight = 0.5, ob.entities = []
                MERGE (b)-[:STATED]->(ob)
                MERGE (od:Opinion {dataset_id: $ds, query_hash: $q_new, round_no: 1, agent_name: 'itest-D'})
                SET od.text = 'dee opinion', od.stance = 'POSITIVE', od.confidence = 0.8,
                    od.weight = 0.5, od.entities = []
                MERGE (d)-[:STATED]->(od)
                """,
                ds=ds, q_new=q_new, q_old=q_old,
            )

        # Current run: the OPPOSES edge is not corroborated (its REACTED_TO is q_old),
        # so A-B is not a neighbour; C-D's same-run REACTED_TO still marks it.
        snap = await memory.read_snapshot(ds, q_new, through_round=1)
        assert "itest-B" not in snap.neighbor_map.get("itest-A", [])
        assert "itest-D" in snap.neighbor_map.get("itest-C", [])

        a_prompt = snap.to_prompt(speaker="itest-A", opponent="itest-B")
        assert "itest-B" in a_prompt
        assert "[directly connected to you]" not in a_prompt  # no cross-run leak

        c_prompt = snap.to_prompt(speaker="itest-C", opponent="itest-D")
        assert "[directly connected to you]" in c_prompt       # same-run REACTED_TO arm

        # The other run sees its own edge and not the current run's.
        snap_old = await memory.read_snapshot(ds, q_old, through_round=1)
        assert "itest-B" in snap_old.neighbor_map.get("itest-A", [])
        assert "itest-D" not in snap_old.neighbor_map.get("itest-C", [])
    finally:
        async with driver.session(database=db) as session:
            await session.run("MATCH (n) WHERE n.dataset_id = $ds DETACH DELETE n", ds=ds)
