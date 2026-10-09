"""Agent.source_evidence: synthesis-time evidence snippets carried to the prompt.

The field grounds an agent's debate prompt in its own real source text. It is
synthesis-time only — it must never be written into the graph.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.persona.agent import (
    SOURCE_EVIDENCE_MAX_SNIPPETS,
    Agent,
    DiscoveryType,
    PersonaIdentity,
)
from src.persona.repository import PersonaRepository


def _agent(**over) -> Agent:
    base = dict(
        identity=PersonaIdentity(name="A", archetype="x", communication_style="y"),
        discovery_type=DiscoveryType.GRAPH_DISCOVERY,
    )
    base.update(over)
    return Agent(**base)


def test_source_evidence_defaults_to_empty_list():
    """Every existing Agent construction still works; evidence starts empty."""
    assert _agent().source_evidence == []


def test_source_evidence_accepts_snippets():
    assert _agent(source_evidence=["a", "b"]).source_evidence == ["a", "b"]


# ---------------------------------------------------------------------------
# Batched fetch: one query for all the persona's chunk texts
# ---------------------------------------------------------------------------


def _repo_returning(rows: list[dict]) -> PersonaRepository:
    """A repository whose driver's session.run yields `rows` — the DB seam."""
    repo = PersonaRepository.__new__(PersonaRepository)
    repo._db = "neo4j"
    session = MagicMock()
    result = MagicMock()
    result.data = AsyncMock(return_value=rows)
    session.run = AsyncMock(return_value=result)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session_cm)
    repo._driver = driver
    return repo


@pytest.mark.asyncio
async def test_fetch_source_evidence_returns_snippets():
    repo = _repo_returning([{"text": "first"}, {"text": "second"}])

    assert await repo.fetch_source_evidence(["c1", "c2"]) == ["first", "second"]


@pytest.mark.asyncio
async def test_fetch_source_evidence_skips_rows_without_text():
    repo = _repo_returning([{"text": "only"}, {"text": None}, {}])

    assert await repo.fetch_source_evidence(["c1", "c2", "c3"]) == ["only"]


@pytest.mark.asyncio
async def test_fetch_source_evidence_empty_ids_makes_no_query():
    repo = _repo_returning([])

    assert await repo.fetch_source_evidence([]) == []
    repo._driver.session.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_source_evidence_is_capped():
    rows = [{"text": f"s{i}"} for i in range(SOURCE_EVIDENCE_MAX_SNIPPETS + 2)]
    repo = _repo_returning(rows)

    out = await repo.fetch_source_evidence([f"c{i}" for i in range(len(rows))])

    assert len(out) == SOURCE_EVIDENCE_MAX_SNIPPETS


@pytest.mark.asyncio
async def test_build_carries_source_evidence_from_chunk_ids():
    """The build path actually consults the persona's chunk ids."""
    repo = PersonaRepository.__new__(PersonaRepository)
    repo.get_provenance = AsyncMock(return_value=[])
    repo.fetch_source_evidence = AsyncMock(return_value=["grounded text"])

    agent = await repo.build_single_agent_profile_from_node(
        agent_name="A",
        node={"name": "A"},
        user_query="q",
        dataset_id="ds",
        agent_metrics={},
        sector_results=[],
        llm_output=None,
        chunk_node_ids=["c1"],
    )

    assert agent.source_evidence == ["grounded text"]
    repo.fetch_source_evidence.assert_awaited_once_with(["c1"])


@pytest.mark.asyncio
async def test_build_without_chunk_ids_has_no_evidence():
    repo = PersonaRepository.__new__(PersonaRepository)
    repo.get_provenance = AsyncMock(return_value=[])

    agent = await repo.build_single_agent_profile_from_node(
        agent_name="A",
        node={"name": "A"},
        user_query="q",
        dataset_id="ds",
        agent_metrics={},
        sector_results=[],
        llm_output=None,
    )

    assert agent.source_evidence == []
