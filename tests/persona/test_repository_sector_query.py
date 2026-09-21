"""Test that find_agent_sectors raises NotImplementedError (migration stub)."""

import pytest

from src.persona.repository import PersonaRepository


@pytest.mark.asyncio
async def test_find_agent_sectors_raises():
    """Confirm the broken Cypher method is replaced with a migration stub."""
    # Credentials are dummies — the method raises before touching the driver.
    repo = PersonaRepository("bolt://localhost:7687", "user", "pass", "neo4j")
    with pytest.raises(NotImplementedError, match="ProfileSynthesizer"):
        await repo.find_agent_sectors(llm_output={}, dataset_id="test")
