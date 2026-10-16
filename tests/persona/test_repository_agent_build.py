"""Real-path agent build: `build_single_agent_profile_from_node` must survive
the metrics shapes `calculate_agent_metrics_and_context_for_llm` actually returns.

`neighbor_context` is a `List[str]` (repository.py ~line 606) while
`context_text` is a string. The perspective branch concatenated them directly
and crashed every real build whose roster had matched sectors — mocked builds
never execute the line, so only a real call catches it.
"""

from unittest.mock import AsyncMock

import pytest

from src.persona.agent import ExpertiseLevel
from src.persona.repository import DistilledProfile, PersonaRepository


def _repo():
    repo = PersonaRepository.__new__(PersonaRepository)
    repo.get_provenance = AsyncMock(return_value=[])
    return repo


async def _build(repo, node, *, distilled=None, agent_metrics=None):
    return await repo.build_single_agent_profile_from_node(
        agent_name=str(node.get("name") or "agent"),
        node=node,
        user_query="q",
        dataset_id="ds",
        agent_metrics=agent_metrics or {},
        sector_results=[],
        llm_output=None,
        distilled=distilled,
    )


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
        sector_results=[
            {
                "domain_tag": "education",
                "total_relevance": 1.0,
                "evidence_nodes": ["Lead"],
                "density": 1,
            }
        ],
        llm_output=None,
    )

    assert "I specialize in education." in agent.detailed_perspective
    assert "Alice (tags: school)" in agent.detailed_perspective


"""Task 5: identity is derived from the graph type + distillation, never a constant."""


@pytest.mark.asyncio
async def test_identity_is_not_a_constant():
    repo = _repo()

    agent = await _build(
        repo, {"name": "Regulator Corp", "label": "Company", "domain_tags": ["banking"]}
    )

    assert agent.identity.archetype == "Company"
    assert agent.identity.archetype != "Strategic Analyst"
    assert agent.identity.communication_style != "strategic and factual"
    assert agent.domain_tags == ["banking"]


@pytest.mark.asyncio
async def test_identity_falls_back_from_type_to_label_to_first_domain_tag():
    """Company type → the type; a bare node → its first domain tag."""
    repo = _repo()

    typed = await _build(repo, {"name": "A", "type_name": "Regulator"})
    tagged = await _build(repo, {"name": "B", "domain_tags": ["energy", "grid"]})

    assert typed.identity.archetype == "Regulator"
    assert tagged.identity.archetype == "energy"  # domain_tags[0], not a constant
    assert tagged.domain_tags == ["energy", "grid"]


@pytest.mark.asyncio
async def test_bare_node_still_builds_a_named_archetype():
    """The last resort is a value, not the erased 'Strategic Analyst' constant."""
    repo = _repo()

    agent = await _build(repo, {"name": "Unknown Entity"})

    assert agent.identity.archetype == "Participant"
    assert agent.expertise_level == ExpertiseLevel.STRATEGIC  # the model's own default


@pytest.mark.asyncio
async def test_distilled_identity_wins_over_the_graph():
    repo = _repo()
    distilled = DistilledProfile(
        "d",
        "p",
        archetype="The Skeptic",
        communication_style="wry and clipped",
        expertise_level="Technical",
        domain_tags=["energy"],
        belief="Incentives shape behaviour.",
        opinion="It will not work here.",
    )

    agent = await _build(
        repo,
        {"name": "Grid Co", "label": "Operator", "domain_tags": ["grid"]},
        distilled=distilled,
    )

    assert agent.identity.archetype == "The Skeptic"
    assert agent.identity.communication_style == "wry and clipped"
    assert agent.expertise_level == ExpertiseLevel.TECHNICAL
    assert agent.domain_tags == ["energy"]
    assert agent.belief == "Incentives shape behaviour."
    assert agent.opinion == "It will not work here."


@pytest.mark.asyncio
async def test_a_silent_distillation_still_falls_back_to_the_graph():
    """An empty DistilledProfile (LLM said nothing) must not blank the identity."""
    repo = _repo()

    agent = await _build(
        repo,
        {"name": "Grid Co", "label": "Operator"},
        distilled=DistilledProfile("d", "p"),
    )

    assert agent.identity.archetype == "Operator"
    assert agent.identity.communication_style == "direct and evidence-led"
