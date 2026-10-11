"""Real-path agent build: `build_single_agent_profile_from_node` must survive
the metrics shapes `calculate_agent_metrics_and_context_for_llm` actually returns.

`neighbor_context` is a `List[str]` (repository.py ~line 606) while
`context_text` is a string. The perspective branch concatenated them directly
and crashed every real build whose roster had matched sectors — mocked builds
never execute the line, so only a real call catches it.
"""
from unittest.mock import AsyncMock

import pytest

from src.persona.repository import PersonaRepository


def _repo():
    repo = PersonaRepository.__new__(PersonaRepository)
    repo.get_provenance = AsyncMock(return_value=[])
    return repo


@pytest.mark.asyncio
async def test_build_joins_list_neighbor_context_into_the_perspective():
    repo = _repo()

    agent = await repo.build_single_agent_profile_from_node(
        agent_name="Lead",
        node={"name": "Lead", "domain_tags": ["resume"]},
        user_query="how is my resume?",
        dataset_id="ds",
        agent_metrics={
            "matched_sectors": ["education"],
            "neighbor_context": ["Alice (tags: school): taught — relations: R1"],
            "context_text": "Matched sectors: education. Top neighbors: Alice.",
        },
        sector_results=[{
            "domain_tag": "education", "total_relevance": 1.0,
            "evidence_nodes": ["Lead"], "density": 1,
        }],
        llm_output=None,
    )

    assert "I specialize in education." in agent.detailed_perspective
    assert "Alice (tags: school)" in agent.detailed_perspective
