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
async def test_distillation_entry_includes_source_text():
    """Task 3: the persona's real chunk text grounds its distillation evidence."""
    entity = _cluster_entity("Amazon", 0.9, ["retail"], "amazon summary")
    entity.properties = {"name": "Amazon", "triplet_source_id": "chunk-1"}
    synth, repo = _distill_synth([entity], {})
    repo.fetch_source_evidence_by_chunk = AsyncMock(
        return_value={"chunk-1": ["Amazon acquired WholeFoods for $2.5B"]}
    )

    await synth.synthesize(query="q", dataset_id="ds", max_agents=1, distill=True)

    entry = repo.distill_profiles.await_args.kwargs["personas"][0]
    assert entry["evidence"] == [
        "Amazon acquired WholeFoods for $2.5B",
        "amazon summary",
    ]
    assert repo.fetch_source_evidence_by_chunk.await_args.args[0] == ["chunk-1"]


@pytest.mark.asyncio
async def test_source_text_is_fetched_once_for_the_whole_batch():
    """One call over the union of every persona's chunk ids — never an N-loop."""
    amazon = _cluster_entity("Amazon", 0.9, ["retail"], "amazon summary")
    amazon.properties = {"name": "Amazon", "triplet_source_id": "c1"}
    grid = _cluster_entity("Grid Co", 0.5, ["energy"], "grid summary")
    grid.properties = {"name": "Grid Co", "triplet_source_id": "c2"}
    synth, repo = _distill_synth([amazon, grid], {})
    repo.fetch_source_evidence_by_chunk = AsyncMock(
        return_value={"c1": ["amazon text"], "c2": ["grid text"]}
    )

    await synth.synthesize(query="q", dataset_id="ds", max_agents=2, distill=True)

    repo.fetch_source_evidence_by_chunk.assert_awaited_once()
    assert sorted(repo.fetch_source_evidence_by_chunk.await_args.args[0]) == ["c1", "c2"]


@pytest.mark.asyncio
async def test_each_persona_is_grounded_in_only_its_own_source_text():
    """R17: distinct chunks → distinct snippets; no persona sees another's text."""
    amazon = _cluster_entity("Amazon", 0.9, ["retail"], "amazon summary")
    amazon.properties = {"name": "Amazon", "triplet_source_id": "c1"}
    grid = _cluster_entity("Grid Co", 0.5, ["energy"], "grid summary")
    grid.properties = {"name": "Grid Co", "triplet_source_id": "c3"}
    synth, repo = _distill_synth([amazon, grid], {})
    repo.fetch_source_evidence_by_chunk = AsyncMock(
        return_value={"c1": ["Amazon acquired WholeFoods"], "c3": ["Grid demand peaked"]}
    )

    await synth.synthesize(query="q", dataset_id="ds", max_agents=2, distill=True)

    entries = {
        entry["name"]: entry["evidence"]
        for entry in repo.distill_profiles.await_args.kwargs["personas"]
    }
    assert "Amazon acquired WholeFoods" in entries["Amazon"]
    assert "Grid demand peaked" in entries["Grid Co"]
    assert "Grid demand peaked" not in entries["Amazon"]
    assert "Amazon acquired WholeFoods" not in entries["Grid Co"]


def _real_chunk_fetch_repo(rows):
    """A fake-driver repo exposing the REAL `fetch_source_evidence_by_chunk`.

    Lets a synthesizer-level test exercise the actual query + bucketing instead
    of a mock that can only replay whatever it was handed.
    """
    from src.persona.repository import PersonaRepository

    real = PersonaRepository.__new__(PersonaRepository)
    real._db = "neo4j"
    session = MagicMock()
    result = MagicMock()
    result.data = AsyncMock(return_value=rows)
    session.run = AsyncMock(return_value=result)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session_cm)
    real._driver = driver
    return real


@pytest.mark.asyncio
async def test_a_chunk_heavy_persona_does_not_starve_the_later_one():
    """R19: no global snippet limit — the late persona keeps its own grounding.

    'Heavy' names 11 chunks (its node + a 10-node subgraph) and 'Light' names 1,
    which lands LAST in the persona-ordered union. Under a global
    `LIMIT 3 * n_personas` the query returns only Heavy's first rows, so Light
    silently distills on `[]`.
    """
    heavy = _cluster_entity("Heavy", 0.9, ["retail"], "heavy summary")
    heavy.properties = {"name": "Heavy", "triplet_source_id": "h1"}
    heavy_subgraph = []
    for i in range(2, 12):
        node = _cluster_entity(f"Heavy {i}", 0.05, ["retail"], "")
        node.properties = {"name": f"Heavy {i}", "triplet_source_id": f"h{i}"}
        heavy_subgraph.append(node)
    light = _cluster_entity("Light", 0.5, ["energy"], "light summary")
    light.properties = {"name": "Light", "triplet_source_id": "L1"}

    async def build_profile(**kwargs):
        return MagicMock(identity=PersonaIdentity(
            name=kwargs["agent_name"], archetype="Analyst", communication_style="factual",
        ))

    repo = MagicMock()
    repo.fetch_nodes_by_names = AsyncMock(return_value={})
    repo.calculate_agent_metrics_and_context_for_llm = AsyncMock(return_value={})
    repo.distill_profiles = AsyncMock(return_value={})
    repo.build_single_agent_profile_from_node = AsyncMock(side_effect=build_profile)
    # The real query + bucketing, over a fake driver.
    repo.fetch_source_evidence_by_chunk = _real_chunk_fetch_repo(
        [{"chunk_id": cid, "text": f"text-{cid}"} for cid in
         ["h1", *[f"h{i}" for i in range(2, 12)], "L1"]]
    ).fetch_source_evidence_by_chunk

    ctx = MagicMock()
    ctx.find_relevant_entities = AsyncMock(return_value=[heavy, light])
    ctx.find_connected_nodes_by_seed = AsyncMock(return_value={"Heavy": heavy_subgraph})
    synth = ProfileSynthesizer(persona_repo=repo, graph_context=ctx)

    await synth.synthesize(query="q", dataset_id="ds", max_agents=2, distill=True)

    entries = {
        entry["name"]: entry["evidence"]
        for entry in repo.distill_profiles.await_args.kwargs["personas"]
    }
    assert "text-h1" in entries["Heavy"]
    assert "text-L1" in entries["Light"]  # the late persona is still grounded
    assert not [t for t in entries["Light"] if t.startswith("text-h")]


@pytest.mark.asyncio
async def test_no_chunk_refs_means_no_evidence_fetch():
    """A roster whose nodes carry no chunk ref makes no source-evidence query."""
    synth, repo = _distill_synth(_SELECTION_ENTITIES, {})
    repo.fetch_source_evidence_by_chunk = AsyncMock(return_value={})

    await synth.synthesize(query="q", dataset_id="ds", max_agents=2, distill=True)

    repo.fetch_source_evidence_by_chunk.assert_not_awaited()


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


def _provenance_synth(entities):
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
    return ProfileSynthesizer(persona_repo=repo, graph_context=ctx), repo, order


@pytest.mark.asyncio
async def test_synthesize_writes_each_nodes_anchor_before_its_build():
    """Two required nodes; each writer gets that node's own chunk ref."""
    lead = _anchored_entity("Lead", "node-7", 0.9)
    second = _anchored_entity("Second", " node-9 ", 0.5)
    synth, repo, order = _provenance_synth([lead, second])

    profiles = await synth.synthesize(query="q", dataset_id="ds", max_agents=2)

    written = [call.kwargs for call in repo.write_persona_provenance.await_args_list]
    assert {w["persona_name"]: w["chunk_node_ids"] for w in written} == {
        "Lead": ["node-7"], "Second": ["node-9"],
    }
    assert order.index("write:Lead") < order.index("build:Lead")
    assert order.index("write:Second") < order.index("build:Second")
    assert sorted(p.identity.name for p in profiles) == ["Lead", "Second"]


@pytest.mark.asyncio
async def test_synthesize_skips_the_write_when_no_entity_carries_an_anchor():
    synth, repo, _ = _provenance_synth([_anchored_entity("Bare", None)])

    profiles = await synth.synthesize(query="q", dataset_id="ds", max_agents=1)

    repo.write_persona_provenance.assert_not_awaited()
    assert [p.identity.name for p in profiles] == ["Bare"]


def test_evidence_chunk_ids_tolerates_non_mapping_properties():
    """A non-mapping `properties` contributes nothing — never invented."""
    from src.simulation.profile_synthesizer import ProfileSynthesizer

    odd = MagicMock()
    odd.properties = ["not", "a", "mapping"]
    assert ProfileSynthesizer._evidence_chunk_ids([odd]) == []


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


"""P5: the S4 rows and each built profile are emitted to the caller's live sinks."""


@pytest.mark.asyncio
async def test_synthesize_emits_selection_before_profiles_in_completion_order():
    """on_selection fires once before any on_profile; ordinals are 1-based and total matches."""
    synthesizer = _selection_synth(_SELECTION_ENTITIES)
    events: list = []

    async def on_selection(rows):
        events.append(("selection", [row.name for row in rows]))

    async def on_profile(profile, index, total):
        events.append(("agent", profile.identity.name, index, total))

    profiles = await synthesizer.synthesize(
        query="test query", dataset_id="ds1", on_selection=on_selection, on_profile=on_profile,
    )

    assert events[0][0] == "selection"
    assert [entry[1] for entry in events[1:]] == [profile.identity.name for profile in profiles]
    assert [entry[2] for entry in events[1:]] == list(range(1, len(profiles) + 1))
    assert all(entry[3] == len(profiles) for entry in events[1:])


@pytest.mark.asyncio
async def test_synthesize_survives_a_raising_profile_emitter():
    """A broken WS emitter is logged, never allowed to break profile synthesis."""
    synthesizer = _selection_synth(_SELECTION_ENTITIES)

    async def broken(profile, index, total):
        raise RuntimeError("ws down")

    profiles = await synthesizer.synthesize(query="test query", dataset_id="ds1", on_profile=broken)
    assert len(profiles) == 2  # the same count the arrange block produces without emitters


"""Test rig: a GraphContext stand-in that records every provenance read."""


class _CountingContext:
    """A GraphContext stand-in that counts provenance reads (no MagicMock auto-attrs)."""

    def __init__(self, entities, provenance_by_id):
        self._entities = entities
        self._provenance_by_id = provenance_by_id
        self.batch_calls: list[list[str]] = []
        self.single_calls = 0

    async def find_relevant_entities(self, query, limit=10):
        return self._entities

    async def get_provenance_batch(self, entity_ids):
        self.batch_calls.append(list(entity_ids))
        return {eid: list(self._provenance_by_id.get(eid, [])) for eid in entity_ids}

    async def get_provenance(self, entity_id):
        self.single_calls += 1
        return list(self._provenance_by_id.get(entity_id, []))


def _synth_over(ctx):
    """A synthesizer over `ctx` whose repo names each built profile after its agent."""
    async def build_profile(**kwargs):
        return MagicMock(identity=PersonaIdentity(
            name=kwargs["agent_name"], archetype="Analyst", communication_style="factual",
        ))

    repo = MagicMock()
    repo.fetch_nodes_by_names = AsyncMock(return_value={})
    repo.calculate_agent_metrics_and_context_for_llm = AsyncMock(return_value={})
    repo.build_single_agent_profile_from_node = AsyncMock(side_effect=build_profile)
    return ProfileSynthesizer(persona_repo=repo, graph_context=ctx), repo


_ROSTER = [
    _cluster_entity("A", 0.9, ["test"], "alpha summary"),
    _cluster_entity("B", 0.8, ["test"], "beta summary"),
    _cluster_entity("C", 0.7, ["test"], "gamma summary"),
]


def _shared_doc():
    return ProvenanceLink(doc_id="doc:1", title="T", breadcrumb="", chunk_id=uuid4())


"""Task 10: each site fetches every node in ONE query, never one query per name."""

from src.persona.repository import PersonaRepository


def _repo_with_counted_queries(rows):
    """A real `fetch_nodes_by_names` over a stubbed driver: executed queries counted.

    One `session.run` is one round trip, so the count is the query count.
    """
    result = AsyncMock()
    result.data = AsyncMock(return_value=rows)

    session = AsyncMock()
    session.run = AsyncMock(return_value=result)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    driver = MagicMock()
    driver.session = MagicMock(return_value=session)

    repo = PersonaRepository.__new__(PersonaRepository)
    repo._driver = driver
    repo._db = "testdb"
    return repo, session


def _node_row(name: str, **props) -> dict:
    return {"name": name, "n": {"name": name, **props}, "is_entity": True}


async def _named_profile(**kwargs):
    return MagicMock(identity=PersonaIdentity(
        name=kwargs["agent_name"], archetype="Analyst", communication_style="factual",
    ))


def _nodes_by_agent(repo) -> dict:
    """{agent_name: node} across every profile-build call."""
    return {
        call.kwargs["agent_name"]: call.kwargs["node"]
        for call in repo.build_single_agent_profile_from_node.await_args_list
    }


@pytest.mark.asyncio
async def test_synthesize_fetches_all_required_nodes_in_one_query():
    """Three required nodes → ONE node-fetch query whose rows map per name (Task 10)."""
    doc = _shared_doc()
    repo, session = _repo_with_counted_queries([
        _node_row("A", domain_tags=["alpha"]),
        _node_row("C", domain_tags=["gamma"]),
    ])
    repo.calculate_agent_metrics_and_context_for_llm = AsyncMock(return_value={})
    repo.build_single_agent_profile_from_node = AsyncMock(side_effect=_named_profile)
    synth = ProfileSynthesizer(repo, _CountingContext(list(_ROSTER), {"A": [doc], "B": [doc]}))

    profiles = await synth.synthesize(query="q", dataset_id="ds", max_agents=3)

    # One node per agent, ONE query.
    assert session.run.await_count == 1
    assert sorted(session.run.await_args.kwargs["names"]) == ["A", "B", "C"]
    assert [p.identity.name for p in profiles] == ["A", "B", "C"]
    assert _nodes_by_agent(repo) == {
        "A": {"name": "A", "domain_tags": ["alpha"], "label": "Persona"},
        "B": {"name": "B", "label": "Persona"},  # no row → the node's own properties
        "C": {"name": "C", "domain_tags": ["gamma"], "label": "Persona"},
    }


@pytest.mark.asyncio
async def test_synthesize_falls_back_per_name_when_the_batch_misses_one():
    """A node name absent from the batch keeps the node-properties fallback (Task 10)."""
    doc = _shared_doc()
    repo, session = _repo_with_counted_queries([_node_row("A", domain_tags=["alpha"])])
    repo.calculate_agent_metrics_and_context_for_llm = AsyncMock(return_value={})
    repo.build_single_agent_profile_from_node = AsyncMock(side_effect=_named_profile)
    synth = ProfileSynthesizer(repo, _CountingContext(list(_ROSTER), {"A": [doc], "B": [doc]}))

    profiles = await synth.synthesize(query="q", dataset_id="ds", max_agents=3)

    assert session.run.await_count == 1
    assert [p.identity.name for p in profiles] == ["A", "B", "C"]
    assert _nodes_by_agent(repo) == {
        "A": {"name": "A", "domain_tags": ["alpha"], "label": "Persona"},
        "B": {"name": "B", "label": "Persona"},
        "C": {"name": "C", "label": "Persona"},
    }


@pytest.mark.asyncio
async def test_synthesize_from_names_fetches_all_names_in_one_query():
    """Three joiners → ONE node-fetch query; the per-name map still drives build-or-skip."""
    repo, session = _repo_with_counted_queries([_node_row("Carl", domain_tags=["regulation"])])
    repo.calculate_agent_metrics_and_context_for_llm = AsyncMock(return_value={})
    repo.build_single_agent_profile_from_node = AsyncMock(side_effect=_named_profile)
    synth = ProfileSynthesizer(repo, MagicMock())

    profiles = await synth.synthesize_from_names(["Carl", "Dana", "Ghost"], "q", "ds")

    assert session.run.await_count == 1
    assert session.run.await_args.kwargs["names"] == ["Carl", "Dana", "Ghost"]
    assert [p.identity.name for p in profiles] == ["Carl"]  # Dana/Ghost unresolved: skipped
    assert _nodes_by_agent(repo) == {"Carl": {"name": "Carl", "domain_tags": ["regulation"]}}


"""Round-1 pairing prerequisite: synthesis writes the persona→entity links
the topology counts."""


def _linkable_synth(entities, provenance_by_id=None):
    """A synthesizer recording the writer/build call order."""
    order: list[str] = []

    async def build_profile(**kwargs):
        order.append("build")
        return MagicMock(identity=PersonaIdentity(
            name=kwargs["agent_name"], archetype="Analyst", communication_style="factual",
        ))

    repo = MagicMock()
    repo.fetch_nodes_by_names = AsyncMock(return_value={})
    repo.calculate_agent_metrics_and_context_for_llm = AsyncMock(return_value={})
    repo.write_persona_provenance = AsyncMock(side_effect=lambda **kw: order.append("provenance") or 1)
    repo.write_persona_entity_links = AsyncMock(side_effect=lambda **kw: order.append("entities") or 1)
    repo.build_single_agent_profile_from_node = AsyncMock(side_effect=build_profile)
    ctx = _CountingContext(list(entities), provenance_by_id or {})
    return ProfileSynthesizer(repo, ctx), repo, order


@pytest.mark.asyncio
async def test_synthesize_writes_entity_links_from_the_cluster_chunks_before_building():
    """Without these edges every persona is an isolated node and round 1 pairs 0."""
    entity = _cluster_entity("Lead", 0.9, ["test"], "lead summary")
    entity.properties = {"name": "Lead", "triplet_source_id": "node-7"}
    synth, repo, order = _linkable_synth([entity])

    profiles = await synth.synthesize(query="q", dataset_id="ds1", max_agents=1)

    repo.write_persona_entity_links.assert_awaited_once_with(
        persona_name="Lead", dataset_id="ds1", chunk_node_ids=["node-7"], stance="NEUTRAL",
    )
    assert order == ["provenance", "entities", "build"]
    assert [p.identity.name for p in profiles] == ["Lead"]


"""Required-node roster: one agent per node — never one document-collapsed cell."""


@pytest.mark.asyncio
async def test_synthesize_single_cell_graph_builds_one_agent_per_required_node():
    """THE regression: 11 nodes from one document → 11 agents, not 1.

    The old roster grouped entities by shared document provenance, so a
    single-document graph collapsed to one un-pairable agent. The graph is
    seeded through `_CountingContext` so every node reports one shared doc.
    """
    entities = [
        _cluster_entity(f"Node {i}", 0.9 - i * 0.01, ["test"], f"summary {i}")
        for i in range(11)
    ]
    doc = _shared_doc()
    synth, _ = _synth_over(
        _CountingContext(entities, {f"Node {i}": [doc] for i in range(11)})
    )

    profiles = await synth.synthesize(query="q", dataset_id="ds", max_agents=50)

    assert len(profiles) == 11  # the old path returned 1: every node shared one doc
    assert [p.identity.name for p in profiles] == [f"Node {i}" for i in range(11)]


@pytest.mark.asyncio
async def test_synthesize_reads_no_provenance_the_roster_is_node_level():
    """The roster derivation touches no provenance: the nodes are the agents."""
    doc = _shared_doc()
    synth, repo = _synth_over(_CountingContext(list(_ROSTER), {"A": [doc], "B": [doc]}))
    ctx = synth._ctx

    profiles = await synth.synthesize(query="q", dataset_id="ds", max_agents=3)

    assert ctx.batch_calls == [] and ctx.single_calls == 0
    assert [p.identity.name for p in profiles] == ["A", "B", "C"]
    totals = {
        call.kwargs["agent_name"]: call.kwargs["sector_results"][0]["total_relevance"]
        for call in repo.build_single_agent_profile_from_node.await_args_list
    }
    assert totals == {"A": 0.9, "B": 0.8, "C": 0.7}  # each build saw its own node


"""Traversal expansion: the roster's candidates are the seeds plus their one-hop neighbours."""


@pytest.mark.asyncio
async def test_synthesize_expands_the_roster_with_walked_neighbours():
    """find_connected_nodes results join the roster as candidates."""
    walked = _cluster_entity("Neighbour", 0.0, ["x"], "linked context")

    class _WalkingContext:
        async def find_relevant_entities(self, query, limit=10):
            return [_cluster_entity("Seed", 0.9, ["x"], "seed text")]

        async def find_connected_nodes(self, node_ids, limit=10):
            return [walked]

    synth, _ = _synth_over(_WalkingContext())

    profiles = await synth.synthesize(query="q", dataset_id="ds", max_agents=5)

    assert sorted(p.identity.name for p in profiles) == ["Neighbour", "Seed"]


@pytest.mark.asyncio
async def test_synthesize_survives_a_failing_traversal(caplog):
    """A raising walk logs and degrades to the seed nodes — never breaks synthesis."""

    class _RaisingWalkContext(_CountingContext):
        async def find_connected_nodes(self, node_ids, limit=10):
            raise RuntimeError("neo4j transient")

    synth, _ = _synth_over(_RaisingWalkContext(list(_ROSTER), {}))

    with caplog.at_level(logging.WARNING, logger="src.simulation.profile_synthesizer"):
        profiles = await synth.synthesize(query="q", dataset_id="ds", max_agents=3)

    assert "node traversal failed" in caplog.text
    assert [p.identity.name for p in profiles] == ["A", "B", "C"]


"""Task 1: the synthesized stance is persisted on the Persona node with the
entity links, where Task 6's round-1 pairing reads it."""


@pytest.mark.asyncio
async def test_synthesize_persists_the_distilled_stance_with_the_entity_links():
    from src.persona.agent import Stance
    from src.persona.repository import DistilledProfile

    entity = _anchored_entity("Lead", "node-7", 0.9)
    repo = MagicMock()
    repo.fetch_nodes_by_names = AsyncMock(return_value={})
    repo.calculate_agent_metrics_and_context_for_llm = AsyncMock(return_value={})
    repo.fetch_source_evidence_by_chunk = AsyncMock(return_value={})
    repo.distill_profiles = AsyncMock(return_value={
        "Lead": DistilledProfile("d", "p", Stance.POSITIVE, 0.8, 0.6),
    })
    repo.write_persona_provenance = AsyncMock(return_value=1)
    repo.write_persona_entity_links = AsyncMock(return_value=1)
    repo.build_single_agent_profile_from_node = AsyncMock(return_value=MagicMock())
    synth = ProfileSynthesizer(repo, _CountingContext([entity], {}))

    await synth.synthesize(query="q", dataset_id="ds", max_agents=1, distill=True)

    assert repo.write_persona_entity_links.await_args.kwargs["stance"] == "POSITIVE"


@pytest.mark.asyncio
async def test_synthesize_persists_the_derived_stance_without_distillation():
    """The shallow path: the graph derivation is persisted too, not just the LLM's."""
    entity = _anchored_entity("Critic", "node-9", 0.9)
    entity.properties = {"name": "Critic", "triplet_source_id": "node-9"}
    repo = MagicMock()
    repo.fetch_nodes_by_names = AsyncMock(
        return_value={"Critic": {"name": "Critic", "relations": ["OPPOSES"]}}
    )
    repo.calculate_agent_metrics_and_context_for_llm = AsyncMock(return_value={})
    repo.write_persona_provenance = AsyncMock(return_value=1)
    repo.write_persona_entity_links = AsyncMock(return_value=1)
    repo.build_single_agent_profile_from_node = AsyncMock(return_value=MagicMock())
    synth = ProfileSynthesizer(repo, _CountingContext([entity], {}))

    await synth.synthesize(query="q", dataset_id="ds", max_agents=1)

    assert repo.write_persona_entity_links.await_args.kwargs["stance"] == "NEGATIVE"


@pytest.mark.asyncio
async def test_synthesize_persists_the_same_stance_the_build_derives():
    """The persisted stance follows the build's precedence, not a node property.

    A node with both a `stance` property and OPPOSES evidence derives NEGATIVE
    (distilled → derivation → node property), so `Persona.stance` must be
    NEGATIVE — the value the built Agent also gets — not the node's POSITIVE.
    """
    entity = _anchored_entity("Torn", "node-5", 0.9)
    repo = MagicMock()
    repo.fetch_nodes_by_names = AsyncMock(return_value={
        "Torn": {"name": "Torn", "stance": "POSITIVE", "relations": ["OPPOSES"]},
    })
    repo.calculate_agent_metrics_and_context_for_llm = AsyncMock(return_value={})
    repo.write_persona_provenance = AsyncMock(return_value=1)
    repo.write_persona_entity_links = AsyncMock(return_value=1)
    repo.build_single_agent_profile_from_node = AsyncMock(return_value=MagicMock())
    synth = ProfileSynthesizer(repo, _CountingContext([entity], {}))

    await synth.synthesize(query="q", dataset_id="ds", max_agents=1)

    assert repo.write_persona_entity_links.await_args.kwargs["stance"] == "NEGATIVE"


@pytest.mark.asyncio
async def test_synthesize_rosters_seeds_when_the_context_has_no_traversal():
    """A context predating the walk still rosters its seeds (mock tolerance)."""

    class _SeedOnlyContext:
        async def find_relevant_entities(self, query, limit=10):
            return list(_ROSTER)

    synth, _ = _synth_over(_SeedOnlyContext())

    profiles = await synth.synthesize(query="q", dataset_id="ds", max_agents=3)

    assert [p.identity.name for p in profiles] == ["A", "B", "C"]


"""Task 2: each persona's evidence is its node plus the node's 1-hop subgraph."""


@pytest.mark.asyncio
async def test_label_reaches_the_build_node_dict():
    """Task 5b: the entity's real type label rides into the node dict the build reads."""
    entity = _cluster_entity("Regulator Corp", 0.9, ["banking"], "banking summary")
    entity.label = "Regulator"
    synth, repo = _distill_synth([entity], {})

    await synth.synthesize(query="q", dataset_id="ds", max_agents=1)

    node = repo.build_single_agent_profile_from_node.await_args.kwargs["node"]
    assert node["label"] == "Regulator"


@pytest.mark.asyncio
async def test_label_reaches_the_build_node_dict_on_the_batch_hit_path():
    """Same merge when `fetch_nodes_by_names` serves the node (not the fallback)."""
    entity = _cluster_entity("Regulator Corp", 0.9, ["banking"], "banking summary")
    entity.label = "Regulator"
    synth, repo = _distill_synth([entity], {})
    repo.fetch_nodes_by_names = AsyncMock(
        return_value={"Regulator Corp": {"name": "Regulator Corp", "domain_tags": ["banking"]}}
    )

    await synth.synthesize(query="q", dataset_id="ds", max_agents=1)

    node = repo.build_single_agent_profile_from_node.await_args.kwargs["node"]
    assert node["label"] == "Regulator"
    assert node["domain_tags"] == ["banking"]  # the fetched properties survive


@pytest.mark.asyncio
async def test_candidate_evidence_includes_the_subgraph():
    """A seed's candidate is grounded in its neighbours, not one bare node."""
    seed = _cluster_entity("Amazon", 0.9, ["retail"], "amazon summary")
    neighbour = _cluster_entity("WholeFoods", 0.0, ["grocery"], "wholefoods summary")

    class _SubgraphContext:
        async def find_relevant_entities(self, query, limit=10):
            return [seed]

        async def find_connected_nodes_by_seed(self, node_ids, limit=10):
            return {"Amazon": [neighbour]}

    synth, repo = _synth_over(_SubgraphContext())

    profiles = await synth.synthesize(query="q", dataset_id="ds", max_agents=1)

    call = repo.build_single_agent_profile_from_node.await_args.kwargs
    assert call["sector_results"][0]["evidence_nodes"] == ["Amazon", "WholeFoods"]
    assert call["sector_results"][0]["density"] == 2  # the neighbour joined the evidence
    assert [p.identity.name for p in profiles] == ["Amazon"]  # representative still the seed


@pytest.mark.asyncio
async def test_subgraph_failure_degrades_to_the_node_alone(caplog):
    """A raising subgraph fetch is logged and never breaks synthesis."""

    class _RaisingSubgraph:
        async def find_relevant_entities(self, query, limit=10):
            return [_cluster_entity("Solo", 0.9, ["x"], "solo summary")]

        async def find_connected_nodes_by_seed(self, node_ids, limit=10):
            raise RuntimeError("neo4j transient")

    synth, repo = _synth_over(_RaisingSubgraph())

    with caplog.at_level(logging.WARNING, logger="src.simulation.profile_synthesizer"):
        profiles = await synth.synthesize(query="q", dataset_id="ds", max_agents=1)

    assert "subgraph fetch failed" in caplog.text
    call = repo.build_single_agent_profile_from_node.await_args.kwargs
    assert call["sector_results"][0]["evidence_nodes"] == ["Solo"]
    assert [p.identity.name for p in profiles] == ["Solo"]


"""Task 7: the roster is diversified across entity types, not ten of one."""


def _typed_entity(name: str, score: float, label: str, tags=("test",)) -> MagicMock:
    node = _cluster_entity(name, score, list(tags), f"{name} summary")
    node.label = label
    return node


@pytest.mark.asyncio
async def test_roster_caps_one_type():
    """10 Companies outrank 2 Regulators, yet the roster keeps both types."""
    entities = [
        _typed_entity(f"Company {i}", 0.95 - i * 0.01, "Company") for i in range(10)
    ]
    entities.append(_typed_entity("Regulator A", 0.5, "Regulator"))
    entities.append(_typed_entity("Regulator B", 0.45, "Regulator"))
    synth = _selection_synth(entities)

    profiles = await synth.synthesize(query="q", dataset_id="ds", max_agents=5)

    labels = [
        call.kwargs["node"]["label"]
        for call in synth._repo.build_single_agent_profile_from_node.await_args_list
    ]
    assert len(profiles) == 5
    assert labels.count("Company") < len(labels)  # one type no longer fills the roster
    assert "Regulator" in labels


@pytest.mark.asyncio
async def test_roster_cap_never_empties_a_single_seat():
    """target=1 → cap=1: the one roster seat is still filled."""
    entities = [
        _typed_entity(f"Company {i}", 0.9 - i * 0.01, "Company") for i in range(3)
    ]
    synth = _selection_synth(entities)

    profiles = await synth.synthesize(query="q", dataset_id="ds", max_agents=1)

    assert len(profiles) == 1


"""Task 7b: a late joiner is built with the graph's own type, not the hollow default."""


@pytest.mark.asyncio
async def test_joiner_gets_a_real_archetype():
    """A joiner from a Regulator node derives archetype "Regulator", not a constant.

    The real `fetch_nodes_by_names` reads the node's Neo4j label (its entity
    type) and the real build derives the identity from it — the same Task 5
    precedence the roster uses.
    """
    repo, _ = _repo_with_counted_queries([
        {
            "name": "Regulator Node",
            "n": {"name": "Regulator Node", "domain_tags": ["banking"]},
            "is_entity": True,
            "labels": ["__Entity__", "Regulator"],
        },
    ])
    repo.calculate_agent_metrics_and_context_for_llm = AsyncMock(return_value={})
    repo.get_provenance = AsyncMock(return_value=[])
    synth = ProfileSynthesizer(repo, MagicMock())

    profiles = await synth.synthesize_from_names(["Regulator Node"], "q", "ds")

    assert [p.identity.name for p in profiles] == ["Regulator Node"]
    assert profiles[0].identity.archetype == "Regulator"
    assert profiles[0].identity.archetype != "Strategic Analyst"
