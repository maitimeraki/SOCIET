"""Batch node fetches read only the caller's dataset (audit C1).

`fetch_nodes_by_names` reads `:__Entity__` nodes only, scoped to the dataset
through their DERIVED_FROM document. `fetch_recent_memories` scopes the agent
and every target it returns. No live Neo4j: the driver is stubbed (the
`recorder` seam in tests/conftest.py, or a fixed result for row shapes).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.graph.scope import entity_in_dataset
from src.persona.repository import PersonaRepository


def _repo_returning(rows) -> PersonaRepository:
    """A repository whose Neo4j seam returns `rows` from the batch fetch."""
    result = AsyncMock()
    result.data = AsyncMock(return_value=rows)
    session = AsyncMock()
    session.run = AsyncMock(return_value=result)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    driver = MagicMock()
    driver.session = MagicMock(return_value=session)

    repo = PersonaRepository.__new__(PersonaRepository)
    repo._driver = driver
    repo._db = "testdb"
    return repo


def _repo_on(recorder) -> PersonaRepository:
    repo = PersonaRepository.__new__(PersonaRepository)
    repo._driver = recorder.driver
    repo._db = "testdb"
    return repo


@pytest.mark.asyncio
async def test_no_collision_names_are_returned_verbatim():
    """A name held by one entity node is returned as that node's props."""
    repo = _repo_returning(
        [
            {
                "name": "Bob",
                "n": {"name": "Bob", "domain_tags": ["energy"]},
                "labels": ["__Entity__", "Company"],
            },
        ]
    )

    out = await repo.fetch_nodes_by_names(["Bob", "Missing"], dataset_id="ds-A")

    assert out == {"Bob": {"name": "Bob", "domain_tags": ["energy"], "label": "Company"}}


@pytest.mark.asyncio
async def test_batch_fetch_reads_only_entities_of_the_dataset(recorder):
    await _repo_on(recorder).fetch_nodes_by_names(["Alice"], dataset_id="ds-A")

    query, params = recorder.calls[0]
    assert "MATCH (n:__Entity__)" in query
    assert entity_in_dataset("n") in query
    assert params["dataset_id"] == "ds-A"


@pytest.mark.asyncio
async def test_batch_fetch_requires_dataset_id(recorder):
    with pytest.raises(TypeError):
        await _repo_on(recorder).fetch_nodes_by_names(["Alice"])


@pytest.mark.asyncio
async def test_recent_memories_scope_the_agent_and_every_target(recorder):
    await _repo_on(recorder).fetch_recent_memories("Alice", dataset_id="ds-A")

    query, params = recorder.calls[0]
    assert entity_in_dataset("n") in query
    assert entity_in_dataset("m") in query
    assert params["dataset_id"] == "ds-A"


@pytest.mark.asyncio
async def test_recent_memories_require_dataset_id(recorder):
    with pytest.raises(TypeError):
        await _repo_on(recorder).fetch_recent_memories("Alice")
