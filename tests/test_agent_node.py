"""
Tests for AgentNode model.
"""
import pytest
from datetime import datetime
from uuid import UUID

from pydantic import ValidationError

from src.simulation.agent_node import AgentNode, Stance


class TestAgentNodeIdentity:
    """Test identity fields."""

    def test_create_minimal_agent(self):
        agent = AgentNode(name="Test Agent", archetype="TEST_TYPE")
        assert agent.name == "Test Agent"
        assert agent.archetype == "TEST_TYPE"
        assert isinstance(agent.id, UUID)
        assert agent.created_at is not None

    def test_identity_fields_present(self):
        agent = AgentNode(
            name="Market Analyst",
            archetype="MARKET_ANALYST",
        )
        assert hasattr(agent, "id")
        assert hasattr(agent, "name")
        assert hasattr(agent, "archetype")
        assert hasattr(agent, "created_at")
        assert hasattr(agent, "updated_at")


class TestAgentNodeStance:
    """Test stance enum and validation."""

    def test_stance_enum_values(self):
        assert Stance.POSITIVE.value == "POSITIVE"
        assert Stance.NEGATIVE.value == "NEGATIVE"
        assert Stance.NEUTRAL.value == "NEUTRAL"
        assert Stance.AMBIVALENT.value == "AMBIVALENT"

    def test_stance_default_is_neutral(self):
        agent = AgentNode(name="Test", archetype="TEST")
        assert agent.stance == Stance.NEUTRAL

    def test_stance_accepts_string_value(self):
        agent = AgentNode(name="Test", archetype="TEST", stance="POSITIVE")
        assert agent.stance == "POSITIVE"


class TestAgentNodeFloatRanges:
    """Test float field range validation."""

    def test_intensity_range_valid(self):
        agent = AgentNode(name="Test", archetype="TEST", intensity=0.7)
        assert agent.intensity == 0.7

    def test_intensity_range_boundary_zero(self):
        agent = AgentNode(name="Test", archetype="TEST", intensity=0.0)
        assert agent.intensity == 0.0

    def test_intensity_range_boundary_one(self):
        agent = AgentNode(name="Test", archetype="TEST", intensity=1.0)
        assert agent.intensity == 1.0

    def test_intensity_out_of_range_above(self):
        with pytest.raises(ValidationError):
            AgentNode(name="Test", archetype="TEST", intensity=1.5)

    def test_intensity_out_of_range_below(self):
        with pytest.raises(ValidationError):
            AgentNode(name="Test", archetype="TEST", intensity=-0.1)

    def test_confidence_range_valid(self):
        agent = AgentNode(name="Test", archetype="TEST", confidence=0.85)
        assert agent.confidence == 0.85

    def test_confidence_out_of_range(self):
        with pytest.raises(ValidationError):
            AgentNode(name="Test", archetype="TEST", confidence=2.0)

    def test_conviction_range_valid(self):
        agent = AgentNode(name="Test", archetype="TEST", conviction=0.9)
        assert agent.conviction == 0.9

    def test_conviction_out_of_range(self):
        with pytest.raises(ValidationError):
            AgentNode(name="Test", archetype="TEST", conviction=-0.5)

    def test_cior_range_full_negative(self):
        agent = AgentNode(name="Test", archetype="TEST", cior=-1.0)
        assert agent.cior == -1.0

    def test_cior_range_full_positive(self):
        agent = AgentNode(name="Test", archetype="TEST", cior=1.0)
        assert agent.cior == 1.0

    def test_cior_range_middle(self):
        agent = AgentNode(name="Test", archetype="TEST", cior=0.0)
        assert agent.cior == 0.0

    def test_cior_out_of_range(self):
        with pytest.raises(ValidationError):
            AgentNode(name="Test", archetype="TEST", cior=1.5)


class TestAgentNodeBCO:
    """Test BCO framework fields."""

    def test_bco_fields_present(self):
        agent = AgentNode(
            name="Test",
            archetype="TEST",
            belief="Market will grow",
            conviction=0.8,
            opinion="Bullish on tech sector",
        )
        assert agent.belief == "Market will grow"
        assert agent.conviction == 0.8
        assert agent.opinion == "Bullish on tech sector"


class TestAgentNodeCIOR:
    """Test CIOR framework fields."""

    def test_cior_field_present(self):
        agent = AgentNode(name="Test", archetype="TEST", cior=0.75)
        assert agent.cior == 0.75

    def test_instinct_tags_default_empty(self):
        agent = AgentNode(name="Test", archetype="TEST")
        assert agent.instinct_tags == []

    def test_instinct_tags_populated(self):
        agent = AgentNode(
            name="Test",
            archetype="TEST",
            instinct_tags=["risk_averse", "growth_seeker"],
        )
        assert len(agent.instinct_tags) == 2
        assert "risk_averse" in agent.instinct_tags


class TestAgentNodeCommunication:
    """Test communication boundary fields."""

    def test_domain_tags_default_empty(self):
        agent = AgentNode(name="Test", archetype="TEST")
        assert agent.domain_tags == []

    def test_domain_tags_populated(self):
        agent = AgentNode(
            name="Test",
            archetype="TEST",
            domain_tags=["finance", "regulation", "technology"],
        )
        assert len(agent.domain_tags) == 3

    def test_entity_affinity_default_empty(self):
        agent = AgentNode(name="Test", archetype="TEST")
        assert agent.entity_affinity == []

    def test_communication_radius_default(self):
        agent = AgentNode(name="Test", archetype="TEST")
        assert agent.communication_radius == 1

    def test_communication_radius_custom(self):
        agent = AgentNode(name="Test", archetype="TEST", communication_radius=3)
        assert agent.communication_radius == 3

    def test_communication_radius_non_negative(self):
        with pytest.raises(ValidationError):
            AgentNode(name="Test", archetype="TEST", communication_radius=-1)


class TestAgentNodeVisibility:
    """Test visibility fields."""

    def test_role_description_default_empty(self):
        agent = AgentNode(name="Test", archetype="TEST")
        assert agent.role_description == ""

    def test_expertise_areas_default_empty(self):
        agent = AgentNode(name="Test", archetype="TEST")
        assert agent.expertise_areas == []

    def test_display_order_default_zero(self):
        agent = AgentNode(name="Test", archetype="TEST")
        assert agent.display_order == 0


class TestAgentNodeDynamic:
    """Test dynamic runtime fields."""

    def test_last_query_default_empty(self):
        agent = AgentNode(name="Test", archetype="TEST")
        assert agent.last_query == ""

    def test_last_response_default_empty(self):
        agent = AgentNode(name="Test", archetype="TEST")
        assert agent.last_response == ""

    def test_activation_count_default_zero(self):
        agent = AgentNode(name="Test", archetype="TEST")
        assert agent.activation_count == 0

    def test_activation_count_non_negative(self):
        with pytest.raises(ValidationError):
            AgentNode(name="Test", archetype="TEST", activation_count=-1)


class TestAgentNodeSerialization:
    """Test serialization and deserialization."""

    def test_to_dict(self):
        agent = AgentNode(
            name="Test Agent",
            archetype="ANALYST",
            stance=Stance.POSITIVE,
            intensity=0.8,
            confidence=0.9,
        )
        data = agent.model_dump()
        assert data["name"] == "Test Agent"
        assert data["archetype"] == "ANALYST"
        assert data["stance"] == "POSITIVE"
        assert data["intensity"] == 0.8

    def test_from_dict(self):
        data = {
            "name": "Test Agent",
            "archetype": "ANALYST",
            "stance": "NEGATIVE",
            "intensity": 0.6,
        }
        agent = AgentNode(**data)
        assert agent.name == "Test Agent"
        assert agent.stance == "NEGATIVE"

    def test_json_serialization(self):
        agent = AgentNode(name="Test", archetype="TEST")
        json_str = agent.model_dump_json()
        assert "Test" in json_str
        assert "TEST" in json_str


class TestAgentNodeComplete:
    """Integration test with all fields."""

    def test_full_agent_creation(self):
        agent = AgentNode(
            name="Sarah Chen",
            archetype="MARKET_ANALYST",
            stance=Stance.POSITIVE,
            intensity=0.85,
            confidence=0.92,
            belief="AI will transform healthcare",
            conviction=0.88,
            opinion="Strong buy on diagnostic AI",
            cior=0.75,
            instinct_tags=["growth_seeker", "tech_enthusiast"],
            domain_tags=["healthcare", "technology", "finance"],
            entity_affinity=["startups", "tech_companies"],
            communication_radius=2,
            role_description="Senior Healthcare Tech Analyst",
            expertise_areas=["AI", "Healthcare", "M&A"],
            display_order=1,
            last_query="Should we invest in diagnostic AI?",
            last_response="Yes, strong buy recommendation",
            activation_count=42,
        )
        assert agent.name == "Sarah Chen"
        assert agent.archetype == "MARKET_ANALYST"
        assert agent.stance == "POSITIVE"
        assert agent.intensity == 0.85
        assert agent.confidence == 0.92
        assert agent.belief == "AI will transform healthcare"
        assert agent.conviction == 0.88
        assert agent.opinion == "Strong buy on diagnostic AI"
        assert agent.cior == 0.75
        assert len(agent.instinct_tags) == 2
        assert len(agent.domain_tags) == 3
        assert agent.communication_radius == 2
        assert agent.activation_count == 42
