"""Tests for find_agent_sectors implementation."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.persona.repository import PersonaRepository


@pytest.mark.asyncio
async def test_find_agent_sectors_returns_sector_results():
    """Verify find_agent_sectors returns properly structured sector results."""
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=AsyncMock(data=AsyncMock(return_value=[
        {"domain_tag": "AI Safety", "total_relevance": 2.5, "evidence_nodes": ["Alice", "Bob"], "density": 3},
        {"domain_tag": "Economics", "total_relevance": 1.8, "evidence_nodes": ["Carol"], "density": 2},
    ])))
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    mock_driver = MagicMock()
    mock_driver.session = MagicMock(return_value=mock_session)

    repo = PersonaRepository.__new__(PersonaRepository)
    repo._driver = mock_driver
    repo._db = "testdb"

    result = await repo.find_agent_sectors(llm_output={}, dataset_id="test_ds")

    assert len(result) == 2
    assert result[0]["domain_tag"] == "AI Safety"
    assert result[0]["total_relevance"] == 2.5
    assert result[1]["domain_tag"] == "Economics"
