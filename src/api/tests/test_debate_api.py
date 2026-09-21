"""
Tests for Debate API endpoints.
"""
import pytest
from fastapi.testclient import TestClient

from src.api.debate_api import (
    router,
    DebateRequest,
    DebateConfigRequest,
    _DEBATE_JOBS,
    _DEBATE_JOBS_LOCK,
    _agent_turn_to_dict,
    _comm_pair_to_dict,
)
from src.simulation.graph_debate_engine import AgentTurn, CommPair


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

    def test_debate_request_custom_values(self):
        """Test custom config values."""
        config = DebateConfigRequest(
            max_agents=25,
            max_rounds=3,
            comm_radius=2,
            min_entity_overlap=2,
            convergence_threshold=0.9,
        )
        assert config.max_agents == 25
        assert config.max_rounds == 3
        assert config.comm_radius == 2
        assert config.min_entity_overlap == 2
        assert config.convergence_threshold == 0.9

    def test_debate_request_validation_max_agents(self):
        """Test max_agents validation."""
        with pytest.raises(Exception):
            DebateConfigRequest(max_agents=200)

    def test_debate_request_validation_threshold(self):
        """Test convergence_threshold validation."""
        with pytest.raises(Exception):
            DebateConfigRequest(convergence_threshold=1.5)


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


class TestHelperFunctions:
    """Test helper functions."""

    def test_agent_turn_to_dict(self):
        """Test AgentTurn serialization."""
        turn = AgentTurn(
            agent_id="agent-1",
            agent_name="Test Agent",
            content="Test content",
            stance="POSITIVE",
            confidence=0.8,
            references=["ref1", "ref2"],
        )
        result = _agent_turn_to_dict(turn)
        assert result["agent_id"] == "agent-1"
        assert result["agent_name"] == "Test Agent"
        assert result["content"] == "Test content"
        assert result["stance"] == "POSITIVE"
        assert result["confidence"] == 0.8
        assert result["references"] == ["ref1", "ref2"]

    def test_comm_pair_to_dict(self):
        """Test CommPair serialization."""
        pair = CommPair(
            agent_a="agent-1",
            agent_b="agent-2",
            shared_entities=["entity1", "entity2"],
            evidence=["evidence1"],
        )
        result = _comm_pair_to_dict(pair)
        assert result["agent_a"] == "agent-1"
        assert result["agent_b"] == "agent-2"
        assert result["shared_entities"] == ["entity1", "entity2"]
        assert result["evidence"] == ["evidence1"]


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
