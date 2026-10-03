"""
Tests for Debate API endpoints.
"""
import asyncio
import json
import uuid
from dataclasses import asdict

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient

from src.api.debate_api import (
    router,
    create_debate,
    stream_debate,
    DebateRequest,
    DebateConfigRequest,
    _run_debate_async,
    _DebateWSManager,
    _DEBATE_JOBS,
    _DEBATE_JOBS_LOCK,
)
from src.simulation.orchestrator import OrchestratedDebateResult
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
from src.simulation.pair_turn import CommPair, DebateVerdict, RoundResult


@pytest.fixture
def client():
    """Create test client.

    FastAPI >=0.135 requires the app-level AsyncExitStack middleware; a bare
    router lacks it ("fastapi_middleware_astack not found in request scope"),
    so the previous `TestClient(router)` could not serve a request at all.
    """
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestRoutesThroughTheApp:
    """The fixture serves the real router inside a real app."""

    def test_unknown_job_is_404(self, client):
        assert client.get("/simulate/no-such-job").status_code == 404

    def test_queued_job_status_is_reported(self, client):
        job_id = f"route-{uuid.uuid4()}"
        _DEBATE_JOBS[job_id] = {
            "job_id": job_id, "status": "queued", "query": "q",
            "graph_id": "ds1", "config": {}, "result": None, "error": None,
        }
        try:
            response = client.get(f"/simulate/{job_id}")
        finally:
            _DEBATE_JOBS.pop(job_id, None)
        assert (response.status_code, response.json()["status"]) == (200, "queued")

    def test_create_debate_rejects_a_blank_query(self, client):
        assert client.post("/simulate/debate", json={"query": "   "}).status_code == 400


class TestDebateRequest:
    """Test DebateRequest model validation."""

    def test_debate_request_defaults(self):
        """Test default values for DebateConfigRequest."""
        config = DebateConfigRequest()
        assert config.max_agents == 50
        assert config.max_rounds == 5
        assert config.comm_radius == 1
        assert config.min_entity_overlap == 1
        assert config.convergence_threshold == 0.8
        assert config.llm_concurrency == 8
        assert config.topology_score_threshold == 0.15

    def test_debate_request_exposes_all_panel_fields(self):
        """All ten UI settings fields are real request fields (§7.4)."""
        config = DebateConfigRequest()
        assert config.max_pairs_per_round == 50
        assert config.max_new_agents_per_round == 2
        assert config.snapshot_top_k == 8

    def test_debate_request_custom_values(self):
        """Test custom config values."""
        config = DebateConfigRequest(
            max_agents=25,
            max_rounds=3,
            comm_radius=2,
            min_entity_overlap=2,
            convergence_threshold=0.9,
            llm_concurrency=16,
            topology_score_threshold=0.25,
        )
        assert config.max_agents == 25
        assert config.max_rounds == 3
        assert config.comm_radius == 2
        assert config.min_entity_overlap == 2
        assert config.convergence_threshold == 0.9
        assert config.llm_concurrency == 16
        assert config.topology_score_threshold == 0.25

    def test_debate_request_validation_max_agents(self):
        """Test max_agents validation."""
        with pytest.raises(Exception):
            DebateConfigRequest(max_agents=200)

    def test_debate_request_validation_threshold(self):
        """Test convergence_threshold validation."""
        with pytest.raises(Exception):
            DebateConfigRequest(convergence_threshold=1.5)

    def test_debate_request_validation_llm_concurrency(self):
        """Test llm_concurrency validation."""
        with pytest.raises(Exception):
            DebateConfigRequest(llm_concurrency=0)
        with pytest.raises(Exception):
            DebateConfigRequest(llm_concurrency=50)

    def test_debate_request_validation_topology_threshold(self):
        """Test topology_score_threshold validation."""
        with pytest.raises(Exception):
            DebateConfigRequest(topology_score_threshold=-0.1)
        with pytest.raises(Exception):
            DebateConfigRequest(topology_score_threshold=1.5)


class TestDebateConfigRequest:
    """Test DebateConfigRequest model."""

    def test_config_request_defaults(self):
        """Test DebateRequest defaults."""
        request = DebateRequest(
            query="Test query?",
            graph_id="test-graph",
        )
        assert request.query == "Test query?"
        assert request.graph_id == "test-graph"
        assert request.selected_domains == []
        assert isinstance(request.config, DebateConfigRequest)

    def test_config_request_validation(self):
        """Test DebateRequest validation."""
        request = DebateRequest(
            query="Test?",
            config=DebateConfigRequest(max_agents=10),
        )
        assert request.config.max_agents == 10


class TestRouterEndpoints:
    """Test router endpoint registration."""

    def test_router_has_debate_endpoint(self):
        """Test that router has debate endpoint."""
        routes = [r.path for r in router.routes]
        # Router has prefix /simulate, so full path is /simulate/debate
        assert "/simulate/debate" in routes

    def test_router_has_job_endpoint(self):
        """Test that router has job status endpoint."""
        routes = [r.path for r in router.routes]
        has_job_id = any("/{job_id}" in r for r in routes)
        assert has_job_id

    def test_router_has_websocket_endpoint(self):
        """Test that router has WebSocket endpoint."""
        routes = [r.path for r in router.routes]
        has_ws = any("/stream" in r for r in routes)
        assert has_ws

    def test_router_prefix(self):
        """Test router has correct prefix."""
        assert router.prefix == "/simulate"

    def test_router_tags(self):
        """Test router has correct tags."""
        assert router.tags == ["debate"]


class TestGraphContextSignature:
    """Test that GraphContext is called with GraphConfig(), not separate params."""

    def test_graph_config_creation(self):
        """Test that GraphConfig creates valid config for GraphContext."""
        from src.graph.config_graph import GraphConfig
        from src.persona.graph_context import GraphContext

        cfg = GraphConfig()
        # GraphContext should accept a GraphConfig object
        assert cfg.neo4j_uri is not None
        assert cfg.neo4j_username is not None
        assert cfg.neo4j_password is not None
        assert cfg.neo4j_database is not None

    @pytest.mark.asyncio
    async def test_graph_context_accepts_config(self):
        """Test that GraphContext.__init__ accepts a GraphConfig parameter."""
        from src.graph.config_graph import GraphConfig
        from src.persona.graph_context import GraphContext
        import inspect

        # Check GraphContext signature
        sig = inspect.signature(GraphContext.__init__)
        params = list(sig.parameters.keys())
        # First param is 'self', second should be 'config'
        assert "config" in params or len(params) >= 2

        # Verify we can create GraphContext with GraphConfig
        cfg = GraphConfig()
        ctx = GraphContext(cfg)
        assert ctx.config is not None


class TestDebateOrchestrator:
    """Test DebateOrchestrator wiring and execution."""

    def test_orchestrator_import(self):
        """Test that DebateOrchestrator can be imported."""
        from src.simulation.orchestrator import DebateOrchestrator
        assert DebateOrchestrator is not None

    @pytest.mark.asyncio
    async def test_orchestrator_run_method_exists(self):
        """Test that orchestrator has run method with expected signature."""
        from src.simulation.orchestrator import DebateOrchestrator
        from src.simulation.profile_synthesizer import ProfileSynthesizer
        from src.simulation.topology import CommunicationTopology
        from src.simulation.llm_batch import BatchedLLMRunner
        from src.simulation.verdict import VerdictSynthesizer
        from src.simulation.society_memory import SocietyMemory
        import inspect

        # Create mock dependencies
        mock_profiler = MagicMock(spec=ProfileSynthesizer)
        mock_topology = MagicMock(spec=CommunicationTopology)
        mock_llm_runner = MagicMock(spec=BatchedLLMRunner)
        mock_verdict = MagicMock(spec=VerdictSynthesizer)
        mock_society_memory = MagicMock(spec=SocietyMemory)

        orchestrator = DebateOrchestrator(
            profile_synthesizer=mock_profiler,
            topology=mock_topology,
            llm_runner=mock_llm_runner,
            verdict_synthesizer=mock_verdict,
            society_memory=mock_society_memory,
        )

        # Verify run method exists
        assert hasattr(orchestrator, 'run')
        sig = inspect.signature(orchestrator.run)
        params = list(sig.parameters.keys())
        assert "query" in params
        assert "dataset_id" in params
        assert "config" in params
        assert "ws_broadcast" in params
        assert "intent" in params


def _stub_profile(name: str) -> Agent:
    return Agent(
        agent_id=uuid.uuid4(),
        identity=PersonaIdentity(name=name, archetype="Expert", communication_style="Formal"),
        discovery_type=DiscoveryType.INTENT_DRIVEN,
        expertise_level=ExpertiseLevel.TECHNICAL,
        bio=f"{name} bio",
        detailed_perspective=f"{name} perspective",
        domain_tags=[f"{name}_domain"],
        confidence=0.7,
        confidence_breakdown=ConfidenceBreakdown(
            source_breadth=1, node_density=1, relationship_connectivity=0.5
        ),
        graph_snapshot=GraphSnapshot(dataset_id="ds1"),
    )


def _stub_verdict() -> DebateVerdict:
    return DebateVerdict(
        overall_stance=Stance.POSITIVE,
        confidence_score=0.9,
        supporting_entities=[],
        opposing_entities=[],
        summary="Test verdict.",
        cluster_details={},
        rounds_executed=1,
    )


_INTENT_REPLY = json.dumps({
    "core_question": "Should we tax carbon?",
    "domain_tags": ["economic"],
    "direct_keywords": ["carbon", "tax"],
    "latent_sectors": [],
    "entity_frame": [],
    "search_perspectives": ["Economic"],
    "stance_axis": "Support = tax carbon.",
})

# The denser cluster is the OFF-topic one, so the intent visibly flips the
# ranking — that is what makes the delivered selection explain the roster.
_SELECTION_ENTITIES = [
    ("Quarterly Logistics Review", 0.9, ["operations"], "quarterly logistics report"),
    ("Carbon Analyst", 0.5, ["economics"], "carbon tax economic policy"),
]


def _selection_entity_nodes():
    nodes = []
    for name, score, tags, summary in _SELECTION_ENTITIES:
        node = MagicMock()
        node.id = name  # unique provenance → each entity is its own cluster
        node.name = name
        node.label = "Persona"
        node.properties = {"name": name}
        node.relevance_score = score
        node.domain_tags = tags
        node.summary = summary
        nodes.append(node)
    return nodes


async def _run_stubbed_job(job_id, config, query="Should we tax carbon?", pre_stored_ws_manager=None):
    """Run the real job path — real orchestrator, S4 selection and S9 wiring —
    with only the graph (Neo4j), round LLM calls and verdict seams stubbed.

    `pre_stored_ws_manager` stands in for a client that connected before the
    task started (`stream_debate` stores its manager on the job).
    """
    llm = MagicMock()
    llm.generate = AsyncMock(return_value=_INTENT_REPLY)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=ctx)
    ctx.__aexit__ = AsyncMock(return_value=False)
    ctx.find_relevant_entities = AsyncMock(return_value=_selection_entity_nodes())

    repo = MagicMock()
    repo.fetch_nodes_by_names = AsyncMock(return_value={})
    repo.calculate_agent_metrics_and_context_for_llm = AsyncMock(return_value={})
    # The product path defaults to depth=standard, so S5 distillation is ON here:
    # the stub repo must satisfy the batch seam (empty result = template path).
    repo.distill_profiles = AsyncMock(return_value={})
    repo.build_single_agent_profile_from_node = AsyncMock(
        side_effect=lambda **kw: _stub_profile(kw["agent_name"])
    )

    topo = MagicMock()
    topo.compute_round_pairs = AsyncMock(return_value=[
        CommPair(agent_a="Carbon Analyst", agent_b="Quarterly Logistics Review",
                 shared_entities=[], score=0.5)
    ])
    verdict_synth = MagicMock()
    verdict_synth.asynthesize = AsyncMock(return_value=_stub_verdict())
    society_memory = MagicMock()
    society_memory.commit_round = AsyncMock(return_value={
        "round": 1, "dataset_id": "ds1", "query_hash": "qh",
        "opinions": 0, "edges": 0, "failed": False,
    })
    ws_manager = MagicMock()
    ws_manager.broadcast = AsyncMock()

    _DEBATE_JOBS[job_id] = {
        "job_id": job_id, "status": "queued", "query": query,
        "graph_id": "ds1", "config": asdict(config), "result": None, "error": None,
    }
    if pre_stored_ws_manager is not None:
        _DEBATE_JOBS[job_id]["ws_manager"] = pre_stored_ws_manager
    try:
        with patch("src.llm.client.LLMClient", return_value=llm), \
             patch("src.persona.graph_context.GraphContext", return_value=ctx), \
             patch("src.persona.repository.PersonaRepository", return_value=repo), \
             patch("src.simulation.topology.CommunicationTopology", return_value=topo), \
             patch("src.simulation.orchestrator.RoundRunner") as rr_cls, \
             patch("src.simulation.verdict.VerdictSynthesizer", return_value=verdict_synth), \
             patch("src.simulation.society_memory.SocietyMemory", return_value=society_memory), \
             patch("src.api.debate_api._DebateWSManager", return_value=ws_manager):
            rr_instance = MagicMock()
            rr_instance.execute_round = AsyncMock(
                return_value=RoundResult(round_num=1, turns=[], pairs=[])
            )
            rr_cls.return_value = rr_instance
            await _run_debate_async(
                job_id=job_id, query=query, graph_id="ds1", config=config,
                selected_domains=None,
            )
    finally:
        job = _DEBATE_JOBS.pop(job_id, None)
    return job, ws_manager


def _stage_events(ws_manager):
    return [
        call.args[0] for call in ws_manager.broadcast.call_args_list
        if call.args and call.args[0].get("type") == "stage"
    ]


class TestDebateJobPayload:
    """S9: the delivered job result self-explains — intent, selection, stage events."""

    @pytest.mark.asyncio
    async def test_job_result_carries_intent_selection_and_stage_events(self):
        job_id = f"payload-{uuid.uuid4()}"
        config = DebateConfig(max_agents=5, max_rounds=1, max_new_agents_per_round=0)

        job, ws_manager = await _run_stubbed_job(job_id, config)

        assert job["status"] == "complete"
        result = job["result"]

        # intent: the real extraction path, persisted on the result
        assert result["intent"]["core_question"] == "Should we tax carbon?"
        assert result["intent"]["extraction_confidence"] == 0.9

        # selection: the S4 decomposition, best first. The intent outranks the
        # denser but off-topic cluster — the payload explains the roster.
        selection = result["selection"]
        assert [row["name"] for row in selection] == [
            "Carbon Analyst", "Quarterly Logistics Review",
        ]
        assert set(selection[0]) >= {"name", "semantic", "density", "blended"}
        assert selection[0]["semantic"] > selection[1]["semantic"]
        assert selection[0]["density"] < selection[1]["density"]
        assert selection[0]["blended"] == pytest.approx(
            0.6 * selection[0]["semantic"] + 0.4 * selection[0]["density"]
        )

        # stage events: real transitions pushed through the job's WS manager
        assert [e["stage"] for e in _stage_events(ws_manager)] == [
            "intake", "selection", "synthesis", "round", "convergence", "verdict",
        ]
        assert [e["index"] for e in _stage_events(ws_manager)] == list(range(6))

        # complete: the verdict rides the wire — same fields as the job result
        complete_msg = next(
            call.args[0] for call in ws_manager.broadcast.call_args_list
            if call.args and call.args[0].get("type") == "complete"
        )
        assert "confidence_score" in complete_msg
        assert "cluster_details" in complete_msg
        assert "supporting_entities" in complete_msg
        assert "opposing_entities" in complete_msg
        assert complete_msg["confidence_score"] == result["confidence_score"] == 0.9

    @pytest.mark.asyncio
    async def test_job_result_warns_when_selection_falls_back_to_density(self):
        """Nothing clears the S4 threshold → the degradation is in the payload."""
        job_id = f"payload-{uuid.uuid4()}"
        config = DebateConfig(
            max_agents=5, max_rounds=1, max_new_agents_per_round=0,
            selection_score_threshold=0.99,
        )

        job, _ = await _run_stubbed_job(job_id, config)

        assert job["status"] == "complete"
        assert any(
            "falling back to density-only ordering" in w
            for w in job["result"]["warnings"]
        )
        # the fallback reorders to density; the decomposition is still delivered
        assert [row["name"] for row in job["result"]["selection"]] == [
            "Quarterly Logistics Review", "Carbon Analyst",
        ]


class TestWSManagerResilience:
    """S9: WS delivery is per-connection and best-effort — the run never depends on it."""

    @pytest.mark.asyncio
    async def test_broadcast_survives_a_disconnected_client(self):
        from src.api.debate_api import _DebateWSManager

        manager = _DebateWSManager()
        dead, alive = MagicMock(), MagicMock()
        dead.send_json = AsyncMock(side_effect=RuntimeError("client gone"))
        alive.send_json = AsyncMock()
        await manager.add(dead)
        await manager.add(alive)

        await manager.broadcast({"type": "stage", "stage": "intake", "index": 0})

        alive.send_json.assert_awaited_once()  # the dead socket does not stop delivery

    @pytest.mark.asyncio
    async def test_a_client_connected_before_the_run_keeps_the_stage_events(self):
        """M1: the job reuses the manager a pre-connected client stored on it."""
        job_id = f"ws-reuse-{uuid.uuid4()}"
        config = DebateConfig(max_agents=5, max_rounds=1, max_new_agents_per_round=0)
        connected = MagicMock()
        connected.broadcast = AsyncMock()

        job, _ = await _run_stubbed_job(job_id, config, pre_stored_ws_manager=connected)

        assert job["status"] == "complete"
        assert [e["stage"] for e in _stage_events(connected)] == [
            "intake", "selection", "synthesis", "round", "convergence", "verdict",
        ]


class TestDebateJobIntent:
    """S3: the job path extracts intent once per run; an LLM outage degrades to the fallback."""

    @pytest.mark.asyncio
    async def test_job_run_uses_fallback_intent_when_llm_fails(self, caplog):
        """A failing provider must not block the debate: fallback intent, run still completes."""
        job_id = f"intent-fallback-{uuid.uuid4()}"
        query = "Should we expand into Europe?"
        config = DebateConfig(max_agents=5, max_rounds=1, max_new_agents_per_round=0)

        failing_llm = MagicMock()
        failing_llm.generate = AsyncMock(side_effect=RuntimeError("provider down"))

        messages: list = []
        ws_manager = MagicMock()

        async def capture(msg):
            messages.append(msg)

        ws_manager.broadcast = capture

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=ctx)
        ctx.__aexit__ = AsyncMock(return_value=False)

        profiler = MagicMock()
        profiler.synthesize = AsyncMock(return_value=[_stub_profile("Alice"), _stub_profile("Bob")])
        topo = MagicMock()
        topo.compute_round_pairs = AsyncMock(return_value=[
            CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[], score=0.5)
        ])
        verdict_synth = MagicMock()
        verdict_synth.asynthesize = AsyncMock(return_value=_stub_verdict())
        society_memory = MagicMock()
        society_memory.commit_round = AsyncMock(return_value={
            "round": 1, "dataset_id": "ds1", "query_hash": "qh",
            "opinions": 0, "edges": 0, "failed": False,
        })

        _DEBATE_JOBS[job_id] = {
            "job_id": job_id, "status": "queued", "query": query,
            "graph_id": "ds1", "config": asdict(config), "result": None, "error": None,
        }
        try:
            with patch("src.llm.client.LLMClient", return_value=failing_llm), \
                 patch("src.persona.graph_context.GraphContext", return_value=ctx), \
                 patch("src.persona.repository.PersonaRepository"), \
                 patch("src.simulation.profile_synthesizer.ProfileSynthesizer", return_value=profiler), \
                 patch("src.simulation.topology.CommunicationTopology", return_value=topo), \
                 patch("src.simulation.verdict.VerdictSynthesizer", return_value=verdict_synth), \
                 patch("src.simulation.society_memory.SocietyMemory", return_value=society_memory), \
                 patch("src.api.debate_api._DebateWSManager", return_value=ws_manager):
                await _run_debate_async(
                    job_id=job_id, query=query, graph_id="ds1",
                    config=config, selected_domains=["legal"],
                )
        finally:
            job = _DEBATE_JOBS.pop(job_id, None)

        assert job["status"] == "complete"
        intent = job["result"]["intent"]
        assert intent["extraction_confidence"] == 0.2  # FALLBACK, not the 0.9 LLM value
        assert intent["core_question"] == query
        assert intent["domain_tags"] == ["legal"]  # selected_domains carried into the fallback
        assert intent["stance_axis"] == ""
        assert "deterministic fallback" in caplog.text
        # S9: the degradation is delivered, not only logged
        assert any(
            "deterministic fallback intent" in w
            for w in job["result"]["warnings"]
        )
        # P5: the S3 intent is the first event on the stream — a client joining
        # later gets it replayed from the buffer.
        assert messages[0]["type"] == "intent"
        assert messages[0]["intent"]["core_question"] == query


class TestSimulationDepth:
    """D3: the request carries the depth gate, defaulting to standard."""

    def test_depth_defaults_to_standard(self):
        assert DebateRequest(query="q").simulation_depth == "standard"

    def test_depth_accepts_the_three_levels(self):
        for depth in ("shallow", "standard", "deep"):
            assert DebateRequest(query="q", simulation_depth=depth).simulation_depth == depth

    def test_depth_rejects_unknown_values(self):
        with pytest.raises(Exception):
            DebateRequest(query="q", simulation_depth="turbo")


async def _run_with_depth(job_id: str, depth: str):
    """Run the real boundary with the orchestrator + repo seams patched.

    Returns what the boundary wired: the finished job, the repository
    constructor call, the orchestrator instance and the run's LLM client.
    """
    llm = MagicMock()
    llm.generate = AsyncMock(return_value=_INTENT_REPLY)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=ctx)
    ctx.__aexit__ = AsyncMock(return_value=False)

    repo = MagicMock()
    result = OrchestratedDebateResult(
        converged=False, verdict="stub", final_stances={}, warnings=[], rounds_executed=0,
    )
    orch = MagicMock()
    orch.run = AsyncMock(return_value=result)
    ws_manager = MagicMock()
    ws_manager.broadcast = AsyncMock()

    _DEBATE_JOBS[job_id] = {
        "job_id": job_id, "status": "queued", "query": "Should we tax carbon?",
        "graph_id": "ds1", "config": {}, "result": None, "error": None,
    }
    try:
        with patch("src.llm.client.LLMClient", return_value=llm), \
             patch("src.persona.graph_context.GraphContext", return_value=ctx), \
             patch("src.persona.repository.PersonaRepository", return_value=repo) as repo_cls, \
             patch("src.simulation.orchestrator.DebateOrchestrator", return_value=orch), \
             patch("src.api.debate_api._DebateWSManager", return_value=ws_manager):
            await _run_debate_async(
                job_id=job_id, query="Should we tax carbon?", graph_id="ds1",
                config=DebateConfig(max_agents=5, max_rounds=1), simulation_depth=depth,
            )
    finally:
        job = _DEBATE_JOBS.pop(job_id, None)
    return job, repo_cls, orch, llm


class TestSimulationDepthGate:
    """D3: shallow → distillation off; standard/deep → on; the client is injected."""

    @pytest.mark.asyncio
    async def test_shallow_turns_distillation_off(self):
        job, repo_cls, orch, llm = await _run_with_depth(f"depth-{uuid.uuid4()}", "shallow")

        assert job["status"] == "complete"
        assert orch.run.await_args.kwargs["distill"] is False
        assert repo_cls.call_args.kwargs["llm_client"] is llm

    @pytest.mark.asyncio
    async def test_standard_and_deep_turn_distillation_on(self):
        for depth in ("standard", "deep"):
            job, repo_cls, orch, llm = await _run_with_depth(f"depth-{depth}-{uuid.uuid4()}", depth)

            assert job["status"] == "complete"
            assert orch.run.await_args.kwargs["distill"] is True
            assert repo_cls.call_args.kwargs["llm_client"] is llm

    @pytest.mark.asyncio
    async def test_create_debate_threads_the_requested_depth_to_the_job(self):
        with patch("src.api.debate_api._run_debate_async", new=AsyncMock()) as runner:
            response = await create_debate(
                DebateRequest(query="Should we tax carbon?", simulation_depth="deep")
            )
            await asyncio.sleep(0)  # let the scheduled job task start
        try:
            assert runner.call_args.kwargs["simulation_depth"] == "deep"
        finally:
            _DEBATE_JOBS.pop(response.job_id, None)


class _DisconnectingWSStub:
    """A WS client that is already gone: `accept` succeeds, the first read disconnects."""

    def __init__(self):
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def receive_text(self):
        raise WebSocketDisconnect()

    async def send_json(self, payload):
        pass


class TestManagerlessJobStream:
    """Re-review obs #1: a client on a job with no manager must not deadlock."""

    @pytest.mark.asyncio
    async def test_managerless_job_registers_a_manager_and_returns(self):
        job_id = f"ws-{uuid.uuid4()}"
        _DEBATE_JOBS[job_id] = {
            "job_id": job_id, "status": "queued", "query": "q",
            "graph_id": "ds1", "config": {}, "result": None, "error": None,
        }
        ws = _DisconnectingWSStub()
        try:
            # Pre-fix the handler re-takes the lock it already holds → hangs here.
            await asyncio.wait_for(stream_debate(ws, job_id), timeout=2)
            registered = _DEBATE_JOBS[job_id].get("ws_manager")
        finally:
            _DEBATE_JOBS.pop(job_id, None)

        assert ws.accepted
        assert isinstance(registered, _DebateWSManager)


class TestWSBufferReplay:
    @pytest.mark.asyncio
    async def test_attach_replays_the_buffer_before_live_events(self):
        manager = _DebateWSManager()
        await manager.broadcast({"type": "stage", "stage": "intake", "index": 0})
        await manager.broadcast({"type": "round", "round": 1, "pairs": [], "turns": []})

        ws = AsyncMock()
        await manager.attach(ws)
        assert [call.args[0]["type"] for call in ws.send_json.call_args_list] == ["stage", "round"]

        await manager.broadcast({"type": "complete", "converged": True})
        assert [call.args[0]["type"] for call in ws.send_json.call_args_list] == ["stage", "round", "complete"]
