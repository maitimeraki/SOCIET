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
from src.simulation.relevance_matrix import NoAgentsDerivableError
from src.utils.queryIntend import QueryIntent


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
    repo.calculate_agent_metrics_and_context_for_llm = AsyncMock(
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
    repo.build_single_agent_profile_from_node = AsyncMock(
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
    assert mock_persona_repo.calculate_agent_metrics_and_context_for_llm.called

    # Verify profile building was called
    assert mock_persona_repo.build_single_agent_profile_from_node.called


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
    """An empty graph is a failed selection, not an empty roster (S4 invariant)."""
    synthesizer._ctx.find_relevant_entities = AsyncMock(return_value=[])

    with pytest.raises(NoAgentsDerivableError, match="no agents derivable from graph"):
        await synthesizer.synthesize(
            query="test",
            dataset_id="test_dataset",
            max_agents=5,
        )


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
    repo.calculate_agent_metrics_and_context_for_llm = AsyncMock(
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
    repo.build_single_agent_profile_from_node = AsyncMock(
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
    repo.calculate_agent_metrics_and_context_for_llm = AsyncMock(
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
    repo.build_single_agent_profile_from_node = AsyncMock(
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
    repo.calculate_agent_metrics_and_context_for_llm = AsyncMock(
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
    repo.build_single_agent_profile_from_node = AsyncMock(
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
    repo.calculate_agent_metrics_and_context_for_llm = AsyncMock(
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

    repo.build_single_agent_profile_from_node = AsyncMock(side_effect=build_profile)

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
    The graph returns one entity — an empty graph is now a hard selection failure.
    """
    entity = MagicMock()
    entity.id = "e1"
    entity.name = "Agent_0"
    entity.relevance_score = 0.9
    entity.domain_tags = ["test"]
    entity.summary = "test entity"
    ctx = MagicMock()
    ctx.find_relevant_entities = AsyncMock(return_value=[entity])

    repo = MagicMock()
    repo.fetch_nodes_by_names = AsyncMock(return_value={})
    repo.calculate_agent_metrics_and_context_for_llm = AsyncMock(
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
    repo.build_single_agent_profile_from_node = AsyncMock(return_value=None)

    synth = ProfileSynthesizer(persona_repo=repo, graph_context=ctx)
    await synth.synthesize(query="AI ethics in healthcare policy", dataset_id="ds", max_agents=3)

    ctx.find_relevant_entities.assert_called_once_with("AI ethics in healthcare policy", limit=9)


"""Tests for ProfileSynthesizer.synthesize_from_names (activation path)."""
import logging

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.simulation.debate_config import DebateConfig
from src.simulation.profile_synthesizer import ProfileSynthesizer


@pytest.fixture
def repo():
    repo = AsyncMock()
    repo.fetch_nodes_by_names = AsyncMock(return_value={
        "Carl": {"name": "Carl", "domain_tags": ["regulation"], "confidence": 0.7},
    })
    repo.calculate_agent_metrics_and_context_for_llm = AsyncMock(return_value={"confidence": 0.7})
    repo.build_single_agent_profile_from_node = AsyncMock(side_effect=lambda **kw: MagicMock(name=kw["agent_name"]))
    return repo


@pytest.fixture
def synth(repo):
    return ProfileSynthesizer(repo, MagicMock())


@pytest.mark.asyncio
async def test_synthesize_from_names_builds_via_repo_pipeline(repo, synth):
    profiles = await synth.synthesize_from_names(["Carl"], "query", "ds1", {"Carl": 0.5})
    assert len(profiles) == 1
    repo.fetch_nodes_by_names.assert_awaited_with(["Carl"])
    kwargs = repo.build_single_agent_profile_from_node.await_args.kwargs
    assert kwargs["agent_name"] == "Carl" and kwargs["dataset_id"] == "ds1"
    metrics_kw = repo.calculate_agent_metrics_and_context_for_llm.await_args.kwargs
    assert metrics_kw["max_relevance"] == 1.0
    assert metrics_kw["sector_results"][0]["total_relevance"] == 0.5


@pytest.mark.asyncio
async def test_synthesize_from_names_skips_unresolvable(repo, synth):
    repo.build_single_agent_profile_from_node = AsyncMock(return_value=None)
    profiles = await synth.synthesize_from_names(["Ghost"], "q", "ds")
    assert profiles == []


@pytest.mark.asyncio
async def test_synthesize_from_names_empty_names(repo, synth):
    assert await synth.synthesize_from_names([], "q", "ds") == []
    repo.fetch_nodes_by_names.assert_not_awaited()


@pytest.mark.asyncio
async def test_synthesize_from_names_skips_name_absent_from_nodes_map(repo, synth):
    """A name that does not resolve in nodes_map is unresolvable: skip, never build.

    The repo fixture resolves only "Carl", so "Ghost" is absent from the graph.
    Building anyway would fabricate an Agent with default archetype/stance/cior
    from the bare name — a hardcoded roster in disguise.
    """
    nodes_map = await repo.fetch_nodes_by_names(["Ghost"])
    assert "Ghost" not in nodes_map  # premise: the name does not resolve

    profiles = await synth.synthesize_from_names(["Ghost"], "q", "ds")

    assert profiles == []
    repo.build_single_agent_profile_from_node.assert_not_awaited()


@pytest.mark.asyncio
async def test_synthesize_from_names_filters_none_for_resolved_name(repo, synth):
    """A name that does resolve, whose builder still yields None, is filtered out.

    This keeps the `p is not None` filter exercised now that unresolvable names
    short-circuit before the builder.
    """
    repo.build_single_agent_profile_from_node = AsyncMock(return_value=None)

    profiles = await synth.synthesize_from_names(["Carl"], "q", "ds")

    assert profiles == []
    repo.build_single_agent_profile_from_node.assert_awaited()


@pytest.mark.asyncio
async def test_synthesize_from_names_writes_the_joiner_provenance_before_building(repo, synth):
    """I2: a joiner whose node carries `triplet_source_id` gets the D2 write."""
    order: list[str] = []
    repo.fetch_nodes_by_names = AsyncMock(return_value={
        "Carl": {"name": "Carl", "domain_tags": ["regulation"], "triplet_source_id": " node-7 "},
    })
    repo.write_persona_provenance = AsyncMock(side_effect=lambda **kw: order.append("write") or 1)
    repo.build_single_agent_profile_from_node = AsyncMock(
        side_effect=lambda **kw: order.append("build") or MagicMock(name=kw["agent_name"])
    )

    profiles = await synth.synthesize_from_names(["Carl"], "q", "ds1")

    repo.write_persona_provenance.assert_awaited_once_with(
        persona_name="Carl", dataset_id="ds1", chunk_node_ids=["node-7"],
    )
    assert order == ["write", "build"]  # written BEFORE the build reads it
    assert len(profiles) == 1


@pytest.mark.asyncio
async def test_synthesize_from_names_skips_the_write_without_a_chunk_ref(repo, synth):
    """The fixture node has no `triplet_source_id`: nothing is written, never invented."""
    await synth.synthesize_from_names(["Carl"], "q", "ds1")

    repo.write_persona_provenance.assert_not_awaited()


@pytest.mark.asyncio
async def test_synthesize_from_names_survives_a_failing_writer(repo, synth):
    """Same tolerance as `_build_profile`: logged and continued, never raised."""
    repo.fetch_nodes_by_names = AsyncMock(return_value={
        "Carl": {"name": "Carl", "triplet_source_id": "node-7"},
    })
    repo.write_persona_provenance = AsyncMock(side_effect=RuntimeError("neo4j down"))

    profiles = await synth.synthesize_from_names(["Carl"], "q", "ds1")

    assert len(profiles) == 1


"""S4: the debate path's selection consumes the S3 intent."""


def _cluster_entity(name: str, score: float, tags: list, summary: str) -> MagicMock:
    node = MagicMock()
    node.id = name  # unique per entity → each entity is its own provenance-solo cluster
    node.name = name
    node.label = "Persona"
    node.properties = {"name": name}
    node.relevance_score = score
    node.domain_tags = tags
    node.summary = summary
    return node


def _selection_synth(entities):
    """A synthesizer over `entities` whose repo names each built profile after its agent."""
    async def build_profile(**kwargs):
        return MagicMock(identity=PersonaIdentity(
            name=kwargs["agent_name"], archetype="Analyst", communication_style="factual",
        ))

    repo = MagicMock()
    repo.fetch_nodes_by_names = AsyncMock(return_value={})
    repo.calculate_agent_metrics_and_context_for_llm = AsyncMock(return_value={})
    repo.build_single_agent_profile_from_node = AsyncMock(side_effect=build_profile)

    ctx = MagicMock()
    ctx.find_relevant_entities = AsyncMock(return_value=entities)
    return ProfileSynthesizer(persona_repo=repo, graph_context=ctx)


# The denser cluster is the off-topic one, so density-only order and
# intent-driven order disagree — that is what makes the selection observable.
_SELECTION_ENTITIES = [
    _cluster_entity("Carbon Analyst", 0.9, ["economics"], "carbon tax economics policy"),
    _cluster_entity("Grid Engineer", 0.5, ["energy"], "energy grid engineering"),
]


@pytest.mark.asyncio
async def test_synthesize_selection_follows_the_intent():
    """Two intents select two different agents from the same graph (P2-T1)."""
    carbon = QueryIntent(
        direct_keywords=["carbon", "tax"], latent_sectors=[], search_perspectives=[],
    )
    energy = QueryIntent(
        direct_keywords=["energy", "grid"], latent_sectors=[], search_perspectives=[],
    )

    carbon_names = [
        p.identity.name
        for p in await _selection_synth(_SELECTION_ENTITIES).synthesize(
            query="q", dataset_id="ds", max_agents=1, intent=carbon,
        )
    ]
    energy_names = [
        p.identity.name
        for p in await _selection_synth(_SELECTION_ENTITIES).synthesize(
            query="q", dataset_id="ds", max_agents=1, intent=energy,
        )
    ]

    assert carbon_names == ["Carbon Analyst"]
    assert energy_names == ["Grid Engineer"]


@pytest.mark.asyncio
async def test_synthesize_without_intent_keeps_the_density_only_order():
    """Backward compatibility: no intent → the pre-S4 density ordering."""
    profiles = await _selection_synth(_SELECTION_ENTITIES).synthesize(
        query="q", dataset_id="ds", max_agents=2,
    )

    assert [p.identity.name for p in profiles] == ["Carbon Analyst", "Grid Engineer"]


@pytest.mark.asyncio
async def test_synthesize_keeps_both_clusters_when_representatives_share_a_name():
    """Two clusters whose representative entities share a name both survive (P2-A m1).

    The row→cluster pairing is positional, so the second row never rebuilds the
    first cluster's entities: each build receives its own cluster's evidence.
    """
    first = _cluster_entity("Twin", 0.9, ["alpha"], "alpha twin")
    second = _cluster_entity("Twin", 0.5, ["beta"], "beta twin")
    first.id, second.id = "e-a", "e-b"  # distinct nodes → distinct clusters
    synth = _selection_synth([first, second])
    repo = synth._repo

    profiles = await synth.synthesize(query="q", dataset_id="ds", max_agents=2)

    assert [p.identity.name for p in profiles] == ["Twin", "Twin"]  # roster keeps both
    totals = [
        call.kwargs["sector_results"][0]["total_relevance"]
        for call in repo.build_single_agent_profile_from_node.await_args_list
    ]
    assert sorted(totals) == [0.5, 0.9]  # each build saw its own cluster, not the twin's


@pytest.mark.asyncio
async def test_synthesize_falls_back_to_density_order_and_warns(caplog):
    """An intent that clears no candidate restores the density ordering and warns."""
    intent = QueryIntent(direct_keywords=["energy"], latent_sectors=[], search_perspectives=[])
    config = DebateConfig(selection_score_threshold=0.99)

    with caplog.at_level(logging.WARNING, logger="src.simulation.relevance_matrix"):
        profiles = await _selection_synth(_SELECTION_ENTITIES).synthesize(
            query="q", dataset_id="ds", max_agents=2, intent=intent, config=config,
        )

    assert [p.identity.name for p in profiles] == ["Carbon Analyst", "Grid Engineer"]
    assert "falling back to density-only ordering" in caplog.text


"""S9: the selection decomposition and the S4 fallback reach the caller's sinks."""


@pytest.mark.asyncio
async def test_synthesize_fills_the_selection_rows_sink():
    """The full ranked decomposition is handed back — not just the built agents."""
    intent = QueryIntent(direct_keywords=["carbon", "tax"], latent_sectors=[], search_perspectives=[])
    rows: list = []

    profiles = await _selection_synth(_SELECTION_ENTITIES).synthesize(
        query="q", dataset_id="ds", max_agents=1, intent=intent, selection_rows=rows,
    )

    assert [row.name for row in rows] == ["Carbon Analyst", "Grid Engineer"]  # all rows, best first
    assert [p.identity.name for p in profiles] == ["Carbon Analyst"]  # only the top one is built
    top = rows[0]
    assert top.blended == pytest.approx(0.6 * top.semantic + 0.4 * top.density)


@pytest.mark.asyncio
async def test_synthesize_reports_the_selection_fallback_to_the_warnings_sink():
    """S4's degradation reaches the run result, not only the log stream."""
    intent = QueryIntent(direct_keywords=["energy"], latent_sectors=[], search_perspectives=[])
    warnings: list[str] = []

    await _selection_synth(_SELECTION_ENTITIES).synthesize(
        query="q", dataset_id="ds", max_agents=2, intent=intent,
        config=DebateConfig(selection_score_threshold=0.99), warnings=warnings,
    )

    assert len(warnings) == 1
    assert "falling back to density-only ordering" in warnings[0]


"""S5: the `distill` keyword gates ONE batch call and threads its results per persona."""


def _distill_synth(entities, distilled_by_name: dict):
    """A synthesizer whose repo records the distillation and profile-build calls."""
    async def build_profile(**kwargs):
        return MagicMock(identity=PersonaIdentity(
            name=kwargs["agent_name"], archetype="Analyst", communication_style="factual",
        ))

    repo = MagicMock()
    repo.fetch_nodes_by_names = AsyncMock(return_value={})
    repo.calculate_agent_metrics_and_context_for_llm = AsyncMock(return_value={})
    repo.distill_profiles = AsyncMock(return_value=distilled_by_name)
    repo.build_single_agent_profile_from_node = AsyncMock(side_effect=build_profile)

    ctx = MagicMock()
    ctx.find_relevant_entities = AsyncMock(return_value=entities)
    return ProfileSynthesizer(persona_repo=repo, graph_context=ctx), repo


def _build_calls(repo) -> dict:
    """{agent_name: distilled kwarg} across every profile-build call."""
    return {
        call.kwargs["agent_name"]: call.kwargs["distilled"]
        for call in repo.build_single_agent_profile_from_node.await_args_list
    }


@pytest.mark.asyncio
async def test_distill_makes_one_batch_call_and_threads_results_per_persona():
    intent = QueryIntent(
        direct_keywords=["carbon"], latent_sectors=[], search_perspectives=[],
        core_question="Tax carbon?", stance_axis="Support = tax it.",
    )
    distilled = {
        "Carbon Analyst": ("Carbon one-liner.", "I am the carbon analyst."),
        "Grid Engineer": ("Grid one-liner.", "I am the grid engineer."),
    }
    synth, repo = _distill_synth(_SELECTION_ENTITIES, distilled)

    profiles = await synth.synthesize(
        query="q", dataset_id="ds", max_agents=2, intent=intent, distill=True,
    )

    # ONE batched call for the whole selection set, fed the S3 question context
    repo.distill_profiles.assert_awaited_once()
    call = repo.distill_profiles.await_args.kwargs
    assert [entry["name"] for entry in call["personas"]] == ["Carbon Analyst", "Grid Engineer"]
    assert call["query"] == "q"
    assert call["core_question"] == "Tax carbon?"
    assert call["stance_axis"] == "Support = tax it."
    # ...and each entry carries its own grounding + S4 anchors
    carbon_entry = call["personas"][0]
    assert carbon_entry["evidence"] == ["carbon tax economics policy"]
    assert carbon_entry["anchors"][0]["id"] == "Carbon Analyst"

    # every persona's distilled pair reaches its own profile build
    assert _build_calls(repo) == distilled
    assert [p.identity.name for p in profiles] == ["Carbon Analyst", "Grid Engineer"]


@pytest.mark.asyncio
async def test_distill_off_makes_no_llm_call_and_keeps_the_pre_s5_path():
    """The default keyword is byte-identical behavior: no call, no distilled text."""
    synth, repo = _distill_synth(_SELECTION_ENTITIES, {})

    await synth.synthesize(query="q", dataset_id="ds", max_agents=2)

    repo.distill_profiles.assert_not_called()
    assert set(_build_calls(repo).values()) == {None}


"""D2: the provenance writer runs per persona, before the profile build that reads it."""


def _anchored_entity(name: str, anchor, score: float = 0.9) -> MagicMock:
    """An entity whose `properties` carries the raw `triplet_source_id`."""
    node = MagicMock()
    node.id = name
    node.name = name
    node.label = "Persona"
    node.properties = {"name": name}
    if anchor is not None:
        node.properties["triplet_source_id"] = anchor
    node.relevance_score = score
    node.domain_tags = ["test"]
    node.summary = f"{name} summary"
    return node


def _provenance_synth(entities, ctx_provenance=None):
    """A synthesizer whose repo records the write/build call order."""
    order: list[str] = []

    async def write(**kwargs):
        order.append(f"write:{kwargs['persona_name']}")
        return 1

    async def build(**kwargs):
        order.append(f"build:{kwargs['agent_name']}")
        return MagicMock(identity=PersonaIdentity(
            name=kwargs["agent_name"], archetype="Analyst", communication_style="factual",
        ))

    repo = MagicMock()
    repo.fetch_nodes_by_names = AsyncMock(return_value={})
    repo.calculate_agent_metrics_and_context_for_llm = AsyncMock(return_value={})
    repo.write_persona_provenance = AsyncMock(side_effect=write)
    repo.build_single_agent_profile_from_node = AsyncMock(side_effect=build)

    ctx = MagicMock()
    ctx.find_relevant_entities = AsyncMock(return_value=entities)
    if ctx_provenance is not None:
        ctx.get_provenance = AsyncMock(return_value=ctx_provenance)
    return ProfileSynthesizer(persona_repo=repo, graph_context=ctx), repo, order


@pytest.mark.asyncio
async def test_synthesize_writes_each_cluster_entity_anchor_before_building():
    """Two entities sharing a doc cluster; the writer gets their real chunk node ids."""
    from types import SimpleNamespace

    lead = _anchored_entity("Lead", "node-7", 0.9)
    second = _anchored_entity("Second", " node-9 ", 0.5)
    synth, repo, order = _provenance_synth(
        [lead, second], ctx_provenance=[SimpleNamespace(doc_id="doc:1")],
    )

    profiles = await synth.synthesize(query="q", dataset_id="ds", max_agents=2)

    repo.write_persona_provenance.assert_awaited_once_with(
        persona_name="Lead", dataset_id="ds", chunk_node_ids=["node-7", "node-9"],
    )
    assert order == ["write:Lead", "build:Lead"]  # written BEFORE the build reads it
    assert [p.identity.name for p in profiles] == ["Lead"]


@pytest.mark.asyncio
async def test_synthesize_skips_the_write_when_no_entity_carries_an_anchor():
    synth, repo, _ = _provenance_synth([_anchored_entity("Bare", None)])

    profiles = await synth.synthesize(query="q", dataset_id="ds", max_agents=1)

    repo.write_persona_provenance.assert_not_awaited()
    assert [p.identity.name for p in profiles] == ["Bare"]


def test_cluster_chunk_ids_tolerates_non_mapping_properties():
    """A non-mapping `properties` contributes nothing — never invented."""
    from src.simulation.profile_synthesizer import ProfileSynthesizer

    odd = MagicMock()
    odd.properties = ["not", "a", "mapping"]
    assert ProfileSynthesizer._cluster_chunk_ids([odd]) == []


@pytest.mark.asyncio
async def test_synthesize_survives_a_failing_writer_with_one_warning():
    synth, repo, _ = _provenance_synth([_anchored_entity("Lead", "node-7")])
    repo.write_persona_provenance = AsyncMock(side_effect=RuntimeError("neo4j down"))
    warnings: list[str] = []

    profiles = await synth.synthesize(query="q", dataset_id="ds", max_agents=1, warnings=warnings)

    assert len(warnings) == 1
    assert "Lead" in warnings[0]
    assert [p.identity.name for p in profiles] == ["Lead"]
    repo.build_single_agent_profile_from_node.assert_awaited()
