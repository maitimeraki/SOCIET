"""S4 on the /hatch surface: find_agent_sectors consumes the intent (or the llm_output dict)."""
import logging

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.persona.repository import PersonaRepository
from src.simulation.debate_config import DebateConfig
from src.utils.queryIntend import QueryIntent

_MATRIX_LOGGER = "src.simulation.relevance_matrix"

SECTOR_ROWS = [
    {"domain_tag": "AI Safety", "total_relevance": 2.5, "evidence_nodes": ["Alice", "Bob"], "density": 3},
    {"domain_tag": "Economics", "total_relevance": 1.8, "evidence_nodes": ["Carol"], "density": 2},
]


def _repo_returning(rows) -> PersonaRepository:
    """A repository whose Neo4j seam returns `rows` — no live database."""
    session = AsyncMock()
    session.run = AsyncMock(return_value=AsyncMock(data=AsyncMock(return_value=rows)))
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    driver = MagicMock()
    driver.session = MagicMock(return_value=session)

    repo = PersonaRepository.__new__(PersonaRepository)
    repo._driver = driver
    repo._db = "testdb"
    return repo


def _intent(*, keywords=(), domains=()) -> QueryIntent:
    return QueryIntent(
        direct_keywords=list(keywords),
        latent_sectors=[],
        search_perspectives=list(domains),
        domain_tags=list(domains),
    )


@pytest.mark.asyncio
async def test_find_agent_sectors_ranks_by_the_intent_and_decomposes_every_row():
    repo = _repo_returning(SECTOR_ROWS)

    result = await repo.find_agent_sectors(
        llm_output={}, dataset_id="ds", intent=_intent(keywords=["economics"]),
    )

    # "Economics" shares nothing with the denser "AI Safety" row's text, so the
    # intent puts it first — the density-only order is the reverse.
    assert [row["domain_tag"] for row in result] == ["Economics", "AI Safety"]
    for row in result:
        selection = row["selection"]
        assert selection["blended"] == pytest.approx(
            DebateConfig().w1 * selection["semantic"] + DebateConfig().w2 * selection["density"]
        )
    assert result[0]["selection"]["semantic"] == 1.0
    assert result[1]["selection"]["density"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_find_agent_sectors_uses_the_llm_output_frame_when_no_intent():
    repo = _repo_returning(SECTOR_ROWS)

    result = await repo.find_agent_sectors(
        llm_output={"direct_keywords": ["economics"], "latent_sectors": [], "search_perspectives": []},
        dataset_id="ds",
    )

    assert [row["domain_tag"] for row in result] == ["Economics", "AI Safety"]


@pytest.mark.asyncio
async def test_find_agent_sectors_without_intent_or_frame_stays_density_ordered():
    repo = _repo_returning(SECTOR_ROWS)

    result = await repo.find_agent_sectors(llm_output={}, dataset_id="ds")

    assert [row["domain_tag"] for row in result] == ["AI Safety", "Economics"]
    assert result[0]["total_relevance"] == 2.5  # the raw row keys survive the ranking
    assert result[0]["evidence_nodes"] == ["Alice", "Bob"]
    assert result[0]["density"] == 3


@pytest.mark.asyncio
async def test_find_agent_sectors_falls_back_to_density_order_and_warns(caplog):
    repo = _repo_returning(SECTOR_ROWS)
    config = DebateConfig(selection_score_threshold=0.99)

    with caplog.at_level(logging.WARNING, logger=_MATRIX_LOGGER):
        result = await repo.find_agent_sectors(
            llm_output={}, dataset_id="ds",
            intent=_intent(keywords=["economics"]), config=config,
        )

    assert [row["domain_tag"] for row in result] == ["AI Safety", "Economics"]
    assert "falling back to density-only ordering" in caplog.text


@pytest.mark.asyncio
async def test_find_agent_sectors_empty_graph_returns_no_rows():
    repo = _repo_returning([])

    assert await repo.find_agent_sectors(llm_output={}, dataset_id="ds") == []
