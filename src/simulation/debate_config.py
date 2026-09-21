from dataclasses import dataclass


@dataclass
class DebateConfig:
    max_agents: int = 50
    max_rounds: int = 5
    comm_radius: int = 1
    min_entity_overlap: int = 1
    max_pairs_per_round: int = 50
    convergence_threshold: float = 0.8
    llm_concurrency: int = 8
    topology_score_threshold: float = 0.15

    def __post_init__(self):
        if not 1 <= self.max_agents <= 100:
            raise ValueError("max_agents must be between 1 and 100")
        if not 1 <= self.max_rounds <= 20:
            raise ValueError("max_rounds must be between 1 and 20")
        if not 1 <= self.comm_radius <= 5:
            raise ValueError("comm_radius must be between 1 and 5")
        if not 1 <= self.min_entity_overlap <= 10:
            raise ValueError("min_entity_overlap must be between 1 and 10")
        if not 1 <= self.max_pairs_per_round <= 200:
            raise ValueError("max_pairs_per_round must be between 1 and 200")
        if not 0.0 <= self.convergence_threshold <= 1.0:
            raise ValueError("convergence_threshold must be between 0.0 and 1.0")
        if not 1 <= self.llm_concurrency <= 32:
            raise ValueError("llm_concurrency must be between 1 and 32")
        if not 0.0 <= self.topology_score_threshold <= 1.0:
            raise ValueError("topology_score_threshold must be between 0.0 and 1.0")
