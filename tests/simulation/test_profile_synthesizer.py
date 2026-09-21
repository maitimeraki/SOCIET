"""Tests for ProfileSynthesizer."""
import asyncio
from uuid import uuid4
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.persona.models_persona import (
    AgentProfile,
    PersonaIdentity,
    DiscoveryType,
    ExpertiseLevel,
    ConfidenceBreakdown,
    ProvenanceLink,
)
from src.simulation.profile_synthesizer import ProfileSynthesizer


@pytest.fixture
def mock_entity_nodes():
    """Create 10 mock EntityNode objects."""
    nodes = []
    for i in range(10):
        node = MagicMock()
        node.id = str(uuid4())
        node.name = f"Agent_{i}"
        node.label = "Persona"
        node.properties = {
            "name": f"Agent_{i}",
            "archetype": "Strategic Analyst",
            "expertise_level": "Strategic",
            "domain_tags": ["ethics", "healthcare"],
            "summary": f"Expert in domain {i}",
        }
        node.relevance_score = 0.5 + (i * 0.05)
        node.summary = f"Expert in domain {i}"
        node.domain_tags = ["ethics", "healthcare"]
        nodes.append(node)
    return nodes


@pytest.fixture
def mock_agent_profile():
    """Create a mock AgentProfile."""
    return AgentProfile(
        discovery_type=DiscoveryType.INTENT_DRIVEN,
        expertise_level=ExpertiseLevel.STRATEGIC,
        identity=PersonaIdentity(
            name="TestAgent",
            archetype="Strategic Analyst",
            communication_style="factual",
        ),
        domain_tags=["ethics", "healthcare"],
        description="Test agent description",
        detailed_perspective="Test perspective",
        confidence=0.75,
        confidence_breakdown=ConfidenceBreakdown(
            source_breadth=3,
            node_density=5,
            relationship_connectivity=0.6,
        ),
        provenance=[],
        last_updated=datetime.utcnow(),
    )


@pytest.fixture
def mock_persona_repo(mock_agent_profile):
    """Create a mock PersonaRepository."""
    repo = MagicMock()
    repo.fetch_nodes_by_names = AsyncMock(return_value={})
    repo._calculate_agent_metrics_and_context_for_llm = AsyncMock(
        return_value={
            "confidence": 0.75,
            "density": 5,
            "connectivity": 0.6,
            "relevance_score": 1.0,
            "matched_sectors": ["ethics", "healthcare"],
            "neighbor_context": [],
            "context_text": "Test context",
        }
    )
    repo._build_single_agent_profile_from_node = AsyncMock(
        return_value=mock_agent_profile
    )
    return repo


@pytest.fixture
def mock_graph_context(mock_entity_nodes):
    """Create a mock GraphContext."""
    ctx = MagicMock()
    ctx.find_relevant_entities = AsyncMock(return_value=mock_entity_nodes)
    return ctx


@pytest.fixture
def synthesizer(mock_persona_repo, mock_graph_context):
    """Create a ProfileSynthesizer with mocks."""
    return ProfileSynthesizer(
        persona_repo=mock_persona_repo,
        graph_context=mock_graph_context,
    )


@pytest.mark.asyncio
async def test_synthesize_returns_list_of_agent_profiles(synthesizer):
    """Verify synthesize returns list of AgentProfile with length <= max_agents."""
    profiles = await synthesizer.synthesize(
        query="AI ethics healthcare",
        dataset_id="test_dataset",
        max_agents=5,
    )

    assert isinstance(profiles, list)
    assert len(profiles) <= 5
    for profile in profiles:
        assert isinstance(profile, AgentProfile)


@pytest.mark.asyncio
async def test_synthesize_calls_graph_context_with_query(synthesizer, mock_graph_context):
    """Verify GraphContext was called with the query."""
    await synthesizer.synthesize(
        query="AI ethics healthcare",
        dataset_id="test_dataset",
        max_agents=5,
    )

    mock_graph_context.find_relevant_entities.assert_called_once_with(
        "AI ethics healthcare",
        limit=15,  # max_agents * 3
    )


@pytest.mark.asyncio
async def test_synthesize_calls_repo_methods(synthesizer, mock_persona_repo):
    """Verify PersonaRepository methods were called with correct args."""
    await synthesizer.synthesize(
        query="AI ethics healthcare",
        dataset_id="test_dataset",
        max_agents=5,
    )

    # Verify fetch_nodes_by_names was called
    assert mock_persona_repo.fetch_nodes_by_names.called

    # Verify metrics calculation was called
    assert mock_persona_repo._calculate_agent_metrics_and_context_for_llm.called

    # Verify profile building was called
    assert mock_persona_repo._build_single_agent_profile_from_node.called


@pytest.mark.asyncio
async def test_synthesize_adaptive_count(synthesizer, mock_graph_context):
    """Verify adaptive count: sqrt(n) * 4, capped at max_agents."""
    # With 10 entities, adaptive count = sqrt(10) * 4 ≈ 12.6 -> capped at 5
    await synthesizer.synthesize(
        query="test query",
        dataset_id="test_dataset",
        max_agents=5,
    )

    # Should have been called with limit = max_agents * 3
    mock_graph_context.find_relevant_entities.assert_called_once()


@pytest.mark.asyncio
async def test_synthesize_empty_entities(synthesizer):
    """Verify synthesize handles empty entity list gracefully."""
    synthesizer._ctx.find_relevant_entities = AsyncMock(return_value=[])

    profiles = await synthesizer.synthesize(
        query="test",
        dataset_id="test_dataset",
        max_agents=5,
    )

    assert profiles == []


@pytest.mark.asyncio
async def test_synthesize_profiles_have_valid_structure(mock_agent_profile):
    """Verify returned profiles have all required AgentProfile fields."""
    profile = mock_agent_profile

    assert hasattr(profile, "identity")
    assert hasattr(profile, "domain_tags")
    assert hasattr(profile, "description")
    assert hasattr(profile, "detailed_perspective")
    assert hasattr(profile, "confidence")
    assert hasattr(profile, "confidence_breakdown")
    assert hasattr(profile, "provenance")

    assert isinstance(profile.identity, PersonaIdentity)
    assert isinstance(profile.confidence_breakdown, ConfidenceBreakdown)
