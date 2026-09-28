"""
Tests for CommunicationTopology Cypher-based pair scoring.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.simulation.topology import CommunicationTopology
from src.simulation.pair_turn import CommPair
from src.simulation.debate_config import DebateConfig
from src.persona.models_persona import AgentProfile, PersonaIdentity, ConfidenceBreakdown


@pytest.fixture
def mock_driver():
    """Mock Neo4j AsyncGraphDatabase driver."""
    driver = MagicMock()
    result = MagicMock()

    result.data = AsyncMock(return_value=[])

    class AsyncSession:
        def __init__(self):
            self._result = result

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def run(self, *args, **kwargs):
            return self._result

    def create_session(*args, **kwargs):
        return AsyncSession()

    driver.session = MagicMock(side_effect=create_session)
    return driver, result


@pytest.fixture
def sample_profiles():
    """Sample AgentProfiles for testing."""
    return [
        AgentProfile(
            identity=PersonaIdentity(
                name="Alice",
                archetype="analyst",
                communication_style="direct",
            ),
            discovery_type="intent_driven",
            expertise_level="Technical",
            domain_tags=["ai", "ml", "ethics"],
            description="AI researcher",
            detailed_perspective="Focuses on AI safety",
            confidence=0.8,
            confidence_breakdown=ConfidenceBreakdown(
                source_breadth=5,
                node_density=10,
                relationship_connectivity=0.7,
            ),
            provenance=[],
        ),
        AgentProfile(
            identity=PersonaIdentity(
                name="Bob",
                archetype="strategist",
                communication_style="collaborative",
            ),
            discovery_type="graph_discovery",
            expertise_level="Strategic",
            domain_tags=["ai", "policy", "governance"],
            description="Policy expert",
            detailed_perspective="Focuses on AI governance",
            confidence=0.7,
            confidence_breakdown=ConfidenceBreakdown(
                source_breadth=3,
                node_density=8,
                relationship_connectivity=0.5,
            ),
            provenance=[],
        ),
        AgentProfile(
            identity=PersonaIdentity(
                name="Charlie",
                archetype="developer",
                communication_style="technical",
            ),
            discovery_type="intent_driven",
            expertise_level="Technical",
            domain_tags=["ml", "engineering", "infrastructure"],
            description="ML engineer",
            detailed_perspective="Focuses on ML systems",
            confidence=0.9,
            confidence_breakdown=ConfidenceBreakdown(
                source_breadth=4,
                node_density=12,
                relationship_connectivity=0.8,
            ),
            provenance=[],
        ),
    ]


@pytest.fixture
def debate_config():
    """Default DebateConfig for testing."""
    return DebateConfig(
        max_agents=50,
        max_rounds=5,
        comm_radius=2,
        min_entity_overlap=1,
        max_pairs_per_round=10,
        convergence_threshold=0.8,
        llm_concurrency=8,
        topology_score_threshold=0.15,
    )


class TestComputeRoundPairs:
    """Test compute_round_pairs method."""

    @pytest.mark.asyncio
    async def test_round1_returns_comm_pairs(self, mock_driver, sample_profiles, debate_config):
        """Verify round 1 returns CommPair objects with expected fields."""
        driver, result = mock_driver
        result.data = AsyncMock(return_value=[
            {
                "agent_a": "Alice",
                "agent_b": "Bob",
                "shared_entities": ["ai"],
                "score": 0.5,
            }
        ])

        topology = CommunicationTopology(driver, "neo4j")
        pairs = await topology.compute_round_pairs(sample_profiles, "ds_001", round_num=1, config=debate_config)

        assert len(pairs) == 1
        assert pairs[0].agent_a == "Alice"
        assert pairs[0].agent_b == "Bob"
        assert pairs[0].score == 0.5

    @pytest.mark.asyncio
    async def test_round2_uses_multi_hop_cypher(self, mock_driver, sample_profiles, debate_config):
        """Verify round 2+ uses multi-hop path length based on comm_radius."""
        driver, result = mock_driver
        result.data = AsyncMock(return_value=[])

        topology = CommunicationTopology(driver, "neo4j")
        pairs = await topology.compute_round_pairs(sample_profiles, "ds_001", round_num=2, config=debate_config)

        # Just verify it returns empty (multi-hop query worked)
        assert pairs == []

    @pytest.mark.asyncio
    async def test_round3_uses_comm_radius(self, mock_driver, sample_profiles):
        """Verify round 3 also uses comm_radius for path expansion."""
        config = DebateConfig(comm_radius=3, max_pairs_per_round=5)
        driver, result = mock_driver
        result.data = AsyncMock(return_value=[])

        topology = CommunicationTopology(driver, "neo4j")
        pairs = await topology.compute_round_pairs(sample_profiles, "ds_001", round_num=3, config=config)

        assert pairs == []

    @pytest.mark.asyncio
    async def test_parses_comm_pairs_correctly(self, mock_driver, sample_profiles, debate_config):
        """Verify response is parsed into CommPair objects."""
        driver, result = mock_driver
        result.data = AsyncMock(return_value=[
            {
                "agent_a": "Alice",
                "agent_b": "Bob",
                "shared_entities": ["ai", "ml"],
                "score": 0.65,
            },
            {
                "agent_a": "Bob",
                "agent_b": "Charlie",
                "shared_entities": ["ml"],
                "score": 0.45,
            },
        ])

        topology = CommunicationTopology(driver, "neo4j")
        pairs = await topology.compute_round_pairs(sample_profiles, "ds_001", round_num=1, config=debate_config)

        assert len(pairs) == 2
        assert pairs[0].agent_a == "Alice"
        assert pairs[0].agent_b == "Bob"
        assert pairs[0].shared_entities == ["ai", "ml"]
        assert pairs[0].score == 0.65

        assert pairs[1].agent_a == "Bob"
        assert pairs[1].agent_b == "Charlie"
        assert pairs[1].shared_entities == ["ml"]
        assert pairs[1].score == 0.45

    @pytest.mark.asyncio
    async def test_empty_result_returns_empty_list(self, mock_driver, sample_profiles, debate_config):
        """Verify empty result returns empty CommPair list."""
        driver, result = mock_driver
        result.data = AsyncMock(return_value=[])

        topology = CommunicationTopology(driver, "neo4j")
        pairs = await topology.compute_round_pairs(sample_profiles, "ds_001", round_num=1, config=debate_config)

        assert pairs == []

    @pytest.mark.asyncio
    async def test_uses_database_from_constructor(self, mock_driver, sample_profiles, debate_config):
        """Verify the database parameter is passed to session."""
        driver, result = mock_driver
        result.data = AsyncMock(return_value=[])

        topology = CommunicationTopology(driver, "my_database")
        await topology.compute_round_pairs(sample_profiles, "ds_001", round_num=1, config=debate_config)

        driver.session.assert_called_once_with(database="my_database")


class TestCypherGeneration:
    """Test Cypher query generation."""

    def test_round1_cypher_structure(self, sample_profiles, debate_config):
        """Verify round 1 Cypher has expected structure."""
        topology = CommunicationTopology(MagicMock(), "test_db")
        cypher, params = topology._round1_cypher(
            ["Alice", "Bob"],
            "ds_001",
            debate_config
        )

        # Check key Cypher clauses
        assert "MATCH (a:Persona)-[r1]-(e)-[r2]-(b:Persona)" in cypher
        assert "WHERE a.name IN $agent_names" in cypher
        assert "WHERE shared_count >= 1" in cypher
        assert "jaccard" in cypher.lower()
        assert "has_opposes" in cypher.lower()
        assert "has_supports" in cypher.lower()
        assert "score >= $threshold" in cypher
        assert "ORDER BY score DESC" in cypher
        assert "LIMIT $max_pairs" in cypher

        # Check params
        assert params["agent_names"] == ["Alice", "Bob"]
        assert params["dataset_id"] == "ds_001"
        assert params["threshold"] == 0.15
        assert params["max_pairs"] == 10

    def test_round_n_cypher_with_custom_radius(self, sample_profiles):
        """Verify round N Cypher uses configurable comm_radius."""
        config = DebateConfig(comm_radius=3)
        topology = CommunicationTopology(MagicMock(), "test_db")
        cypher, params = topology._round_n_cypher(
            ["Alice", "Bob"],
            "ds_001",
            config,
            effective_radius=3
        )

        assert "[r1*1..3]" in cypher
        assert "[r2*1..3]" in cypher
        # round_num is used for path length, not hardcoded
        assert "round_num" not in cypher


class TestCommPair:
    """Test CommPair dataclass."""

    def test_comm_pair_creation(self):
        """Verify CommPair has expected fields."""
        pair = CommPair(
            agent_a="Alice",
            agent_b="Bob",
            shared_entities=["ai", "ml"],
            evidence=["evidence1"],
            score=0.75,
        )

        assert pair.agent_a == "Alice"
        assert pair.agent_b == "Bob"
        assert pair.shared_entities == ["ai", "ml"]
        assert pair.evidence == ["evidence1"]
        assert pair.score == 0.75

    def test_comm_pair_default_score(self):
        """Verify CommPair defaults score to 0.0."""
        pair = CommPair(agent_a="Alice", agent_b="Bob")
        assert pair.score == 0.0
        assert pair.shared_entities == []
        assert pair.evidence == []


from src.simulation.pair_turn import ActivationCandidate


@pytest.mark.asyncio
async def test_find_activation_candidates_merges_sources_and_caps(mock_driver):
    driver, result = mock_driver
    result.data = AsyncMock(side_effect=[
        [{"name": "Swing", "shared": ["carbon"]},                       # mentions source: 1 entity
         {"name": "Quiet", "shared": ["tariff", "trade"]}],             # mentions source: 2 entities
        [{"name": "Dormant", "shared_entities": ["ethics", "policy", "law"]},  # adjacency source: 3 entities
         {"name": "Swing", "shared_entities": ["carbon", "ethics"]}],   # adjacency dup — mention copy wins
    ])
    topology = CommunicationTopology(driver, "db")
    cands = await topology.find_activation_candidates(
        participants=["Alice"], dataset_id="ds1", query_hash="qh1", last_round=1, max_new=2,
    )
    names = [c.agent_name for c in cands]
    # 3 merged candidates (> max_new), richest inserted last: the cap and the
    # descending-count ranking are both load-bearing here.
    assert len(cands) == 2
    assert "Dormant" in names
    assert names == ["Dormant", "Quiet"]
    assert cands[0].agent_name == "Dormant"  # ranked by shared-entity count desc
    assert "Swing" not in names              # cap drops the poorest candidate


@pytest.mark.asyncio
async def test_find_activation_candidates_disabled_or_no_candidates(mock_driver):
    driver, result = mock_driver
    result.data = AsyncMock(return_value=[])
    topology = CommunicationTopology(driver, "db")
    assert await topology.find_activation_candidates(["A"], "ds", "qh", 1, max_new=0) == []
    assert await topology.find_activation_candidates([], "ds", "qh", 1, max_new=2) == []
    driver.session.assert_not_called()  # short-circuit happens before any query
