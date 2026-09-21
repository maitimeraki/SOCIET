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
