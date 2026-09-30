"""
Tests for Debate API endpoints.
"""
import uuid
from dataclasses import asdict

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from src.api.debate_api import (
    router,
    DebateRequest,
    DebateConfigRequest,
    _run_debate_async,
    _DEBATE_JOBS,
    _DEBATE_JOBS_LOCK,
)
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
from src.simulation.pair_turn import CommPair, DebateVerdict


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(router)


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
                 patch("src.simulation.society_memory.SocietyMemory", return_value=society_memory):
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
