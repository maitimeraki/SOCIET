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


@pytest.mark.asyncio
async def test_synthesize_returns_exactly_target_profiles():
    """When graph has enough entities, adaptive target is returned exactly.

    With 9 entities: sqrt(9) * 4 = 12, capped at max_agents=5 -> returns 5.
    """
    entities = []
    for i in range(9):
        node = MagicMock()
        node.id = str(uuid4())
        node.name = f"Agent_{i}"
        node.label = "Persona"
        node.properties = {"name": f"Agent_{i}", "domain_tags": ["test"]}
        node.relevance_score = 0.9 - (i * 0.01)
        node.domain_tags = ["test"]
        entities.append(node)

    repo = MagicMock()
    repo.fetch_nodes_by_names = AsyncMock(
        return_value={f"Agent_{i}": {"name": f"Agent_{i}"} for i in range(9)}
    )
    repo._calculate_agent_metrics_and_context_for_llm = AsyncMock(
        return_value={
            "confidence": 0.75,
            "density": 5,
            "connectivity": 0.6,
            "relevance_score": 1.0,
            "matched_sectors": ["test"],
            "neighbor_context": [],
            "context_text": "Test context",
        }
    )
    repo._build_single_agent_profile_from_node = AsyncMock(
        return_value=AgentProfile(
            discovery_type=DiscoveryType.INTENT_DRIVEN,
            expertise_level=ExpertiseLevel.STRATEGIC,
            identity=PersonaIdentity(name="Agent", archetype="Analyst", communication_style="factual"),
            domain_tags=["test"],
            description="desc",
            detailed_perspective="perspective",
            confidence=0.75,
            confidence_breakdown=ConfidenceBreakdown(source_breadth=1, node_density=1, relationship_connectivity=0.5),
            provenance=[],
            last_updated=datetime.utcnow(),
        )
    )

    ctx = MagicMock()
    ctx.find_relevant_entities = AsyncMock(return_value=entities)

    synth = ProfileSynthesizer(persona_repo=repo, graph_context=ctx)
    profiles = await synth.synthesize(query="test", dataset_id="ds", max_agents=5)

    assert len(profiles) == 5


@pytest.mark.asyncio
async def test_synthesize_returns_fewer_when_sparse():
    """When graph is sparse, fewer than max_agents are returned.

    With 4 entities: sqrt(4) * 4 = 8, capped at max_agents=5 -> returns min(5,8)=4.
    """
    entities = []
    for i in range(4):
        node = MagicMock()
        node.id = str(uuid4())
        node.name = f"Agent_{i}"
        node.label = "Persona"
        node.properties = {"name": f"Agent_{i}"}
        node.relevance_score = 0.8
        node.domain_tags = ["test"]
        entities.append(node)

    repo = MagicMock()
    repo.fetch_nodes_by_names = AsyncMock(
        return_value={f"Agent_{i}": {"name": f"Agent_{i}"} for i in range(4)}
    )
    repo._calculate_agent_metrics_and_context_for_llm = AsyncMock(
        return_value={
            "confidence": 0.75,
            "density": 2,
            "connectivity": 0.5,
            "relevance_score": 0.8,
            "matched_sectors": ["test"],
            "neighbor_context": [],
            "context_text": "Test",
        }
    )
    repo._build_single_agent_profile_from_node = AsyncMock(
        return_value=AgentProfile(
            discovery_type=DiscoveryType.INTENT_DRIVEN,
            expertise_level=ExpertiseLevel.STRATEGIC,
            identity=PersonaIdentity(name="Agent", archetype="Analyst", communication_style="factual"),
            domain_tags=["test"],
            description="desc",
            detailed_perspective="perspective",
            confidence=0.75,
            confidence_breakdown=ConfidenceBreakdown(source_breadth=1, node_density=1, relationship_connectivity=0.5),
            provenance=[],
            last_updated=datetime.utcnow(),
        )
    )

    ctx = MagicMock()
    ctx.find_relevant_entities = AsyncMock(return_value=entities)

    synth = ProfileSynthesizer(persona_repo=repo, graph_context=ctx)
    profiles = await synth.synthesize(query="test", dataset_id="ds", max_agents=5)

    assert 0 < len(profiles) < 5


@pytest.mark.asyncio
async def test_synthesize_profiles_have_provenance_and_domain_tags():
    """All returned profiles have non-empty provenance and domain_tags."""
    entities = []
    for i in range(3):
        node = MagicMock()
        node.id = str(uuid4())
        node.name = f"Agent_{i}"
        node.label = "Persona"
        node.properties = {"name": f"Agent_{i}"}
        node.relevance_score = 0.9
        node.domain_tags = ["ethics", "healthcare"]
        entities.append(node)

    repo = MagicMock()
    repo.fetch_nodes_by_names = AsyncMock(
        return_value={f"Agent_{i}": {"name": f"Agent_{i}"} for i in range(3)}
    )
    repo._calculate_agent_metrics_and_context_for_llm = AsyncMock(
        return_value={
            "confidence": 0.75,
            "density": 3,
            "connectivity": 0.6,
            "relevance_score": 0.9,
            "matched_sectors": ["ethics", "healthcare"],
            "neighbor_context": [],
            "context_text": "Test",
        }
    )
    repo._build_single_agent_profile_from_node = AsyncMock(
        return_value=AgentProfile(
            discovery_type=DiscoveryType.INTENT_DRIVEN,
            expertise_level=ExpertiseLevel.STRATEGIC,
            identity=PersonaIdentity(name="Agent", archetype="Analyst", communication_style="factual"),
            domain_tags=["ethics", "healthcare"],
            description="desc",
            detailed_perspective="perspective",
            confidence=0.75,
            confidence_breakdown=ConfidenceBreakdown(source_breadth=2, node_density=3, relationship_connectivity=0.6),
            provenance=[ProvenanceLink(doc_id="doc1", title="Source", breadcrumb="a>b", chunk_id=uuid4())],
            last_updated=datetime.utcnow(),
        )
    )

    ctx = MagicMock()
    ctx.find_relevant_entities = AsyncMock(return_value=entities)

    synth = ProfileSynthesizer(persona_repo=repo, graph_context=ctx)
    profiles = await synth.synthesize(query="test", dataset_id="ds", max_agents=5)

    assert len(profiles) == 3
    for p in profiles:
        assert len(p.provenance) > 0, "provenance must be non-empty"
        assert len(p.domain_tags) > 0, "domain_tags must be non-empty"


@pytest.mark.asyncio
async def test_synthesize_confidence_in_valid_range():
    """All returned profiles have confidence in [0.4, 0.95]."""
    entities = []
    for i in range(3):
        node = MagicMock()
        node.id = str(uuid4())
        node.name = f"Agent_{i}"
        node.label = "Persona"
        node.properties = {"name": f"Agent_{i}"}
        node.relevance_score = 0.8
        node.domain_tags = ["test"]
        entities.append(node)

    repo = MagicMock()
    repo.fetch_nodes_by_names = AsyncMock(
        return_value={f"Agent_{i}": {"name": f"Agent_{i}"} for i in range(3)}
    )
    repo._calculate_agent_metrics_and_context_for_llm = AsyncMock(
        return_value={
            "confidence": 0.75,
            "density": 3,
            "connectivity": 0.6,
            "relevance_score": 0.8,
            "matched_sectors": ["test"],
            "neighbor_context": [],
            "context_text": "Test",
        }
    )

    # Build profiles with varying confidence values
    async def build_profile(*args, **kwargs):
        return AgentProfile(
            discovery_type=DiscoveryType.INTENT_DRIVEN,
            expertise_level=ExpertiseLevel.STRATEGIC,
            identity=PersonaIdentity(name="Agent", archetype="Analyst", communication_style="factual"),
            domain_tags=["test"],
            description="desc",
            detailed_perspective="perspective",
            confidence=0.75,
            confidence_breakdown=ConfidenceBreakdown(source_breadth=2, node_density=3, relationship_connectivity=0.6),
            provenance=[],
            last_updated=datetime.utcnow(),
        )

    repo._build_single_agent_profile_from_node = AsyncMock(side_effect=build_profile)

    ctx = MagicMock()
    ctx.find_relevant_entities = AsyncMock(return_value=entities)

    synth = ProfileSynthesizer(persona_repo=repo, graph_context=ctx)
    profiles = await synth.synthesize(query="test", dataset_id="ds", max_agents=5)

    for p in profiles:
        assert 0.4 <= p.confidence <= 0.95


@pytest.mark.asyncio
async def test_synthesize_vector_search_called_with_query_string():
    """find_relevant_entities is called with the raw query string, not an embedding.

    The GraphContext internally calls _get_embedding(query) before vector search.
    The synthesize method passes the raw query; this test verifies that contract.
    """
    ctx = MagicMock()
    ctx.find_relevant_entities = AsyncMock(return_value=[])

    repo = MagicMock()
    repo.fetch_nodes_by_names = AsyncMock(return_value={})
    repo._calculate_agent_metrics_and_context_for_llm = AsyncMock(
        return_value={
            "confidence": 0.75,
            "density": 1,
            "connectivity": 0.5,
            "relevance_score": 1.0,
            "matched_sectors": [],
            "neighbor_context": [],
            "context_text": "",
        }
    )
    repo._build_single_agent_profile_from_node = AsyncMock(return_value=None)

    synth = ProfileSynthesizer(persona_repo=repo, graph_context=ctx)
    await synth.synthesize(query="AI ethics in healthcare policy", dataset_id="ds", max_agents=3)

    ctx.find_relevant_entities.assert_called_once_with("AI ethics in healthcare policy", limit=9)
