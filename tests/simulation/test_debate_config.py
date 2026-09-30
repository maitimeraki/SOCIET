import pytest
from src.simulation.debate_config import DebateConfig


class TestDebateConfig:
    def test_default_constructs_valid(self):
        config = DebateConfig()
        assert config.max_agents == 50
        assert config.max_rounds == 5
        assert config.comm_radius == 1
        assert config.min_entity_overlap == 1
        assert config.max_pairs_per_round == 50
        assert config.convergence_threshold == 0.8
        assert config.llm_concurrency == 8
        assert config.topology_score_threshold == 0.15

    def test_llm_concurrency_bounds(self):
        with pytest.raises(ValueError, match="llm_concurrency must be between 1 and 32"):
            DebateConfig(llm_concurrency=0)
        with pytest.raises(ValueError, match="llm_concurrency must be between 1 and 32"):
            DebateConfig(llm_concurrency=33)
        DebateConfig(llm_concurrency=1)
        DebateConfig(llm_concurrency=32)

    def test_topology_score_threshold_bounds(self):
        with pytest.raises(ValueError, match="topology_score_threshold must be between 0.0 and 1.0"):
            DebateConfig(topology_score_threshold=-0.1)
        with pytest.raises(ValueError, match="topology_score_threshold must be between 0.0 and 1.0"):
            DebateConfig(topology_score_threshold=1.1)
        DebateConfig(topology_score_threshold=0.0)
        DebateConfig(topology_score_threshold=1.0)


class TestDebateConfigDefaults:
    """Tests for default values."""

    def test_default_values(self):
        """Test that defaults are set correctly."""
        config = DebateConfig()
        assert config.max_agents == 50
        assert config.max_rounds == 5
        assert config.comm_radius == 1
        assert config.min_entity_overlap == 1
        assert config.max_pairs_per_round == 50
        assert config.convergence_threshold == 0.8


class TestDebateConfigValidation:
    """Tests for validation."""

    def test_max_agents_valid(self):
        """Test max_agents valid range."""
        config = DebateConfig(max_agents=1)
        assert config.max_agents == 1
        config = DebateConfig(max_agents=100)
        assert config.max_agents == 100
        config = DebateConfig(max_agents=50)
        assert config.max_agents == 50

    def test_max_agents_invalid_low(self):
        """Test max_agents rejects values below 1."""
        with pytest.raises(ValueError, match="max_agents"):
            DebateConfig(max_agents=0)

    def test_max_agents_invalid_high(self):
        """Test max_agents rejects values above 100."""
        with pytest.raises(ValueError, match="max_agents"):
            DebateConfig(max_agents=101)

    def test_max_rounds_valid(self):
        """Test max_rounds valid range."""
        config = DebateConfig(max_rounds=1)
        assert config.max_rounds == 1
        config = DebateConfig(max_rounds=20)
        assert config.max_rounds == 20

    def test_max_rounds_invalid_low(self):
        """Test max_rounds rejects values below 1."""
        with pytest.raises(ValueError, match="max_rounds"):
            DebateConfig(max_rounds=0)

    def test_max_rounds_invalid_high(self):
        """Test max_rounds rejects values above 20."""
        with pytest.raises(ValueError, match="max_rounds"):
            DebateConfig(max_rounds=21)

    def test_comm_radius_valid(self):
        """Test comm_radius valid range."""
        config = DebateConfig(comm_radius=1)
        assert config.comm_radius == 1
        config = DebateConfig(comm_radius=5)
        assert config.comm_radius == 5

    def test_comm_radius_invalid_low(self):
        """Test comm_radius rejects values below 1."""
        with pytest.raises(ValueError, match="comm_radius"):
            DebateConfig(comm_radius=0)

    def test_comm_radius_invalid_high(self):
        """Test comm_radius rejects values above 5."""
        with pytest.raises(ValueError, match="comm_radius"):
            DebateConfig(comm_radius=6)

    def test_min_entity_overlap_valid(self):
        """Test min_entity_overlap valid range."""
        config = DebateConfig(min_entity_overlap=1)
        assert config.min_entity_overlap == 1
        config = DebateConfig(min_entity_overlap=10)
        assert config.min_entity_overlap == 10

    def test_min_entity_overlap_invalid_low(self):
        """Test min_entity_overlap rejects values below 1."""
        with pytest.raises(ValueError, match="min_entity_overlap"):
            DebateConfig(min_entity_overlap=0)

    def test_min_entity_overlap_invalid_high(self):
        """Test min_entity_overlap rejects values above 10."""
        with pytest.raises(ValueError, match="min_entity_overlap"):
            DebateConfig(min_entity_overlap=11)

    def test_max_pairs_per_round_valid(self):
        """Test max_pairs_per_round valid range."""
        config = DebateConfig(max_pairs_per_round=1)
        assert config.max_pairs_per_round == 1
        config = DebateConfig(max_pairs_per_round=200)
        assert config.max_pairs_per_round == 200

    def test_max_pairs_per_round_invalid_low(self):
        """Test max_pairs_per_round rejects values below 1."""
        with pytest.raises(ValueError, match="max_pairs_per_round"):
            DebateConfig(max_pairs_per_round=0)

    def test_max_pairs_per_round_invalid_high(self):
        """Test max_pairs_per_round rejects values above 200."""
        with pytest.raises(ValueError, match="max_pairs_per_round"):
            DebateConfig(max_pairs_per_round=201)

    def test_convergence_threshold_valid(self):
        """Test convergence_threshold valid range."""
        config = DebateConfig(convergence_threshold=0.0)
        assert config.convergence_threshold == 0.0
        config = DebateConfig(convergence_threshold=1.0)
        assert config.convergence_threshold == 1.0
        config = DebateConfig(convergence_threshold=0.5)
        assert config.convergence_threshold == 0.5

    def test_convergence_threshold_invalid_low(self):
        """Test convergence_threshold rejects negative values."""
        with pytest.raises(ValueError, match="convergence_threshold"):
            DebateConfig(convergence_threshold=-0.1)

    def test_convergence_threshold_invalid_high(self):
        """Test convergence_threshold rejects values above 1.0."""
        with pytest.raises(ValueError, match="convergence_threshold"):
            DebateConfig(convergence_threshold=1.1)

    def test_multiple_invalid_fields_raises_first(self):
        """Test that first invalid field raises."""
        with pytest.raises(ValueError) as exc_info:
            DebateConfig(max_agents=0, max_rounds=0)
        # Should raise on first field only
        assert "max_agents" in str(exc_info.value)

    def test_all_valid_values_accepted(self):
        """Test that all valid values together are accepted."""
        config = DebateConfig(
            max_agents=75,
            max_rounds=15,
            comm_radius=3,
            min_entity_overlap=5,
            max_pairs_per_round=100,
            convergence_threshold=0.85,
        )
        assert config.max_agents == 75
        assert config.max_rounds == 15
        assert config.comm_radius == 3
        assert config.min_entity_overlap == 5
        assert config.max_pairs_per_round == 100
        assert config.convergence_threshold == 0.85


def test_new_loop_fields_defaults():
    cfg = DebateConfig()
    assert cfg.max_new_agents_per_round == 2
    assert cfg.snapshot_top_k == 8


def test_new_loop_fields_validated():
    with pytest.raises(ValueError):
        DebateConfig(max_new_agents_per_round=11)
    with pytest.raises(ValueError):
        DebateConfig(snapshot_top_k=4)
