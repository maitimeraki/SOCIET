"""Re-review obs #2: a name held by both a `:Persona` and a `:__Entity__` node.

`fetch_nodes_by_names` matches on the bare `name` property, and round commits
create `:Persona` nodes — so on a repeat run a name can resolve to either
shape. The entity row must win deterministically, whatever order the driver
returns the rows in, or the I2 joiner write silently degrades.

No live Neo4j: the driver is stubbed (same seam as `test_repository_provenance`).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.persona.repository import PersonaRepository

ENTITY_ROW = {
    "name": "Alice",
    "n": {"name": "Alice", "triplet_source_id": "src-1", "domain_tags": ["energy"]},
    "is_entity": True,
}
PERSONA_ROW = {
    "name": "Alice",
    "n": {"name": "Alice", "stance": "NEGATIVE", "conviction": 0.5},
    "is_entity": False,
}


def _repo_returning(rows) -> tuple[PersonaRepository, AsyncMock]:
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
    return repo, session


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rows",
    [[ENTITY_ROW, PERSONA_ROW], [PERSONA_ROW, ENTITY_ROW]],
    ids=["entity-row-first", "persona-row-first"],
)
async def test_entity_row_wins_whatever_the_row_order(rows):
    repo, session = _repo_returning(rows)

    out = await repo.fetch_nodes_by_names(["Alice"])

    assert out["Alice"]["triplet_source_id"] == "src-1"
    assert "stance" not in out["Alice"]
    # The label predicate is what makes the preference knowable per row.
    assert "n:__Entity__ AS is_entity" in session.run.await_args.args[0]


@pytest.mark.asyncio
async def test_no_collision_names_are_returned_verbatim():
    """A name held by one node only is unchanged — and still returned."""
    repo, _ = _repo_returning([
        {"name": "Bob", "n": {"name": "Bob", "domain_tags": ["energy"]}, "is_entity": False},
    ])

    out = await repo.fetch_nodes_by_names(["Bob", "Missing"])

    assert out == {"Bob": {"name": "Bob", "domain_tags": ["energy"]}}
