"""Tests for Agent API endpoints."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest_asyncio
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

load_dotenv()

from src.api.agent_api import (
    router,
    _agent_to_dict,
    _turn_to_dict,
    AgentUpdateRequest,
    AgentResponse,
    AgentHistoryResponse,
    AgentListResponse,
)
from src.simulation.agent_node import AgentNode, Stance
from src.persona.response_tracker import AgentTurn
from datetime import datetime


# Test fixtures
@pytest.fixture
def sample_agent() -> AgentNode:
    """Create a sample agent for testing."""
    return AgentNode(
        name="Test Analyst",
        archetype="MARKET_ANALYST",
        stance=Stance.NEUTRAL,
        intensity=0.6,
        confidence=0.7,
        belief="Markets are efficient",
        conviction=0.8,
        opinion="",
        cior=0.2,
        instinct_tags=["risk_aware", "data_driven"],
        domain_tags=["finance", "markets"],
        entity_affinity=["Company", "Market"],
        communication_radius=2,
        role_description="Expert in market analysis",
        expertise_areas=["equities", "derivatives"],
        display_order=1,
    )


@pytest.fixture
def sample_turn() -> AgentTurn:
    """Create a sample agent turn for testing."""
    return AgentTurn(
        agent_id="test-agent-id",
        query="What is the market outlook?",
        response="The market shows positive trends.",
        timestamp=datetime.utcnow(),
        stance=Stance.POSITIVE,
        confidence=0.8,
        round=1,
    )


class TestAgentToDict:
    """Tests for _agent_to_dict helper."""

    def test_converts_agent_to_dict(self, sample_agent):
        """Test that _agent_to_dict correctly serializes an AgentNode."""
        result = _agent_to_dict(sample_agent)

        assert result["id"] == str(sample_agent.id)
        assert result["name"] == sample_agent.name
        assert result["archetype"] == sample_agent.archetype
        # stance is already string due to use_enum_values=True
        assert result["stance"] == sample_agent.stance
        assert result["intensity"] == sample_agent.intensity
        assert result["confidence"] == sample_agent.confidence
        assert result["belief"] == sample_agent.belief
        assert result["cior"] == sample_agent.cior
        assert result["domain_tags"] == sample_agent.domain_tags
        assert result["instinct_tags"] == sample_agent.instinct_tags

    def test_includes_dynamic_fields(self, sample_agent):
        """Test that dynamic fields are included in output."""
        sample_agent.last_query = "Test query"
        sample_agent.last_response = "Test response"
        sample_agent.activation_count = 5

        result = _agent_to_dict(sample_agent)

        assert result["last_query"] == "Test query"
        assert result["last_response"] == "Test response"
        assert result["activation_count"] == 5


class TestTurnToDict:
    """Tests for _turn_to_dict helper."""

    def test_converts_turn_to_dict(self, sample_turn):
        """Test that _turn_to_dict correctly serializes an AgentTurn."""
        result = _turn_to_dict(sample_turn)

        assert result["agent_id"] == sample_turn.agent_id
        assert result["query"] == sample_turn.query
        assert result["response"] == sample_turn.response
        assert result["timestamp"] == sample_turn.timestamp.isoformat()
        assert result["stance"] == sample_turn.stance.value
        assert result["confidence"] == sample_turn.confidence
        assert result["round"] == sample_turn.round


class TestAgentUpdateRequest:
    """Tests for AgentUpdateRequest model."""

    def test_all_fields_optional(self):
        """Test that all fields are optional."""
        request = AgentUpdateRequest()
        assert request.name is None
        assert request.stance is None
        assert request.cior is None

    def test_valid_stance_values(self):
        """Test that valid stance values are accepted."""
        for stance in [Stance.POSITIVE, Stance.NEGATIVE, Stance.NEUTRAL, Stance.AMBIVALENT]:
            request = AgentUpdateRequest(stance=stance)
            assert request.stance == stance

    def test_valid_intensity_range(self):
        """Test that intensity is validated."""
        request = AgentUpdateRequest(intensity=0.5)
        assert request.intensity == 0.5

    def test_intensity_out_of_range_rejected(self):
        """Test that out-of-range intensity is rejected."""
        with pytest.raises(ValueError):
            AgentUpdateRequest(intensity=1.5)


class TestAgentResponses:
    """Tests for response models."""

    def test_agent_list_response(self, sample_agent):
        """Test AgentListResponse model."""
        response = AgentListResponse(
            agents=[_agent_to_dict(sample_agent)],
            total=1,
        )
        assert len(response.agents) == 1
        assert response.total == 1

    def test_agent_response(self, sample_agent):
        """Test AgentResponse model."""
        response = AgentResponse(agent=_agent_to_dict(sample_agent))
        assert response.agent["name"] == sample_agent.name

    def test_agent_history_response(self, sample_turn):
        """Test AgentHistoryResponse model."""
        response = AgentHistoryResponse(history=[_turn_to_dict(sample_turn)])
        assert len(response.history) == 1
        assert response.history[0]["query"] == sample_turn.query


class TestAgentAPIErrors:
    """Tests for API error handling."""

    @pytest.mark.asyncio
    async def test_get_agent_not_found(self):
        """Test 404 response when agent doesn't exist."""
        from src.api.agent_api import get_agent

        with patch("src.api.agent_api.AgentRepository") as mock_repo:
            mock_instance = AsyncMock()
            mock_instance.get_agent.return_value = None
            mock_repo.return_value = mock_instance

            try:
                result = await get_agent("nonexistent-id")
            except Exception as e:
                # Expected to raise HTTPException
                from fastapi import HTTPException
                assert isinstance(e, HTTPException)
                assert e.status_code == 404

    @pytest.mark.asyncio
    async def test_update_agent_not_found(self):
        """Test 404 response when updating non-existent agent."""
        from src.api.agent_api import update_agent

        with patch("src.api.agent_api.AgentRepository") as mock_repo:
            mock_instance = AsyncMock()
            mock_instance.get_agent.return_value = None
            mock_repo.return_value = mock_instance

            try:
                result = await update_agent(
                    "nonexistent-id",
                    AgentUpdateRequest(cior=0.5)
                )
            except Exception as e:
                from fastapi import HTTPException
                assert isinstance(e, HTTPException)
                assert e.status_code == 404

    @pytest.mark.asyncio
    async def test_history_agent_not_found(self):
        """Test 404 response when getting history for non-existent agent."""
        from src.api.agent_api import get_agent_history, GraphConfig, AgentRepository, ResponseTracker

        # Create separate mocks for the two calls
        with patch.object(AgentRepository, "get_agent", new_callable=AsyncMock) as mock_get, \
             patch.object(ResponseTracker, "get_response_history", new_callable=AsyncMock):
            mock_get.return_value = None

            try:
                result = await get_agent_history("nonexistent-id")
            except Exception as e:
                from fastapi import HTTPException
                assert isinstance(e, HTTPException)
                assert e.status_code == 404


class TestAgentAPIWithMocks:
    """Integration-style tests with mocked repositories."""

    @pytest.mark.asyncio
    async def test_list_agents_returns_agents(self, sample_agent):
        """Test list_agents returns agents correctly."""
        from src.api.agent_api import list_agents

        with patch("src.api.agent_api.AgentRepository") as mock_repo:
            mock_instance = AsyncMock()
            mock_instance.list_agents.return_value = [sample_agent]
            mock_repo.return_value = mock_instance

            result = await list_agents()

            assert result.total == 1
            assert len(result.agents) == 1
            assert result.agents[0]["name"] == sample_agent.name

    @pytest.mark.asyncio
    async def test_get_agent_returns_agent(self, sample_agent):
        """Test get_agent returns agent correctly."""
        from src.api.agent_api import get_agent

        with patch("src.api.agent_api.AgentRepository") as mock_repo:
            mock_instance = AsyncMock()
            mock_instance.get_agent.return_value = sample_agent
            mock_repo.return_value = mock_instance

            result = await get_agent(str(sample_agent.id))

            assert result.agent["name"] == sample_agent.name
            assert result.agent["archetype"] == sample_agent.archetype

    @pytest.mark.asyncio
    async def test_update_agent_modifies_fields(self, sample_agent):
        """Test update_agent modifies fields correctly."""
        from src.api.agent_api import update_agent

        updated_agent = AgentNode(
            id=sample_agent.id,
            name=sample_agent.name,
            archetype=sample_agent.archetype,
            stance=Stance.POSITIVE,
            intensity=0.9,
            confidence=sample_agent.confidence,
            belief=sample_agent.belief,
            conviction=sample_agent.conviction,
            opinion=sample_agent.opinion,
            cior=0.5,
        )

        with patch("src.api.agent_api.AgentRepository") as mock_repo:
            mock_instance = AsyncMock()
            mock_instance.get_agent.return_value = sample_agent
            mock_instance.update_agent.return_value = updated_agent
            mock_repo.return_value = mock_instance

            result = await update_agent(
                str(sample_agent.id),
                AgentUpdateRequest(cior=0.5, stance=Stance.POSITIVE)
            )

            assert result.agent["cior"] == 0.5
            assert result.agent["stance"] == "POSITIVE"

    @pytest.mark.asyncio
    async def test_get_history_returns_turns(self, sample_turn):
        """Test get_agent_history returns history correctly."""
        from src.api.agent_api import get_agent_history

        with patch("src.api.agent_api.AgentRepository") as mock_repo, \
             patch("src.api.agent_api.ResponseTracker") as mock_tracker:
            mock_instance = AsyncMock()
            mock_instance.get_agent.return_value = MagicMock()
            mock_repo.return_value = mock_instance

            tracker_instance = AsyncMock()
            tracker_instance.get_response_history.return_value = [sample_turn]
            mock_tracker.return_value = tracker_instance

            result = await get_agent_history("test-agent-id", limit=10)

            assert len(result.history) == 1
            assert result.history[0]["query"] == sample_turn.query

    @pytest.mark.asyncio
    async def test_list_agents_with_filters(self, sample_agent):
        """Test list_agents with filter parameters."""
        from src.api.agent_api import list_agents

        with patch("src.api.agent_api.AgentRepository") as mock_repo:
            mock_instance = AsyncMock()
            mock_instance.list_agents.return_value = [sample_agent]
            mock_repo.return_value = mock_instance

            result = await list_agents(
                archetype="MARKET_ANALYST",
                stance="NEUTRAL",
                min_confidence=0.5,
                limit=50,
                offset=0,
            )

            # Verify filters were passed
            mock_instance.list_agents.assert_called_once()
            call_kwargs = mock_instance.list_agents.call_args[0][0]
            assert call_kwargs["archetype"] == "MARKET_ANALYST"
            assert call_kwargs["limit"] == 50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
