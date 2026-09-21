"""
Tests for Debate API endpoints.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from src.api.debate_api import (
    router,
    DebateRequest,
    DebateConfigRequest,
    _DEBATE_JOBS,
    _DEBATE_JOBS_LOCK,
)


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
        from src.simulation.writeback import WriteBackService
        import inspect

        # Create mock dependencies
        mock_profiler = MagicMock(spec=ProfileSynthesizer)
        mock_topology = MagicMock(spec=CommunicationTopology)
        mock_llm_runner = MagicMock(spec=BatchedLLMRunner)
        mock_verdict = MagicMock(spec=VerdictSynthesizer)
        mock_writeback = MagicMock(spec=WriteBackService)

        orchestrator = DebateOrchestrator(
            profile_synthesizer=mock_profiler,
            topology=mock_topology,
            llm_runner=mock_llm_runner,
            verdict_synthesizer=mock_verdict,
            writeback=mock_writeback,
        )

        # Verify run method exists
        assert hasattr(orchestrator, 'run')
        sig = inspect.signature(orchestrator.run)
        params = list(sig.parameters.keys())
        assert "query" in params
        assert "dataset_id" in params
        assert "config" in params
        assert "ws_broadcast" in params
