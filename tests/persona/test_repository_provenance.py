"""D2: the provenance writer — real `(Persona)-[:MENTIONS]->(Chunk)` edges.

The read path (`get_provenance`) already exists; these tests pin the write
statement, its bounds, and the seam where the two meet (chunk node ids in,
real `chunk.chunk_id`s out). No live Neo4j: the driver is stubbed.
"""
from uuid import UUID

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.persona.repository import PersonaRepository

CHUNK_UUID = "3f1d2c9a-0000-4000-8000-000000000001"


def _repo_capturing(rows=None) -> tuple[PersonaRepository, AsyncMock]:
    """A repository whose Neo4j seam records the statement it runs."""
    result = AsyncMock()
    result.data = AsyncMock(return_value=[{"written": 2}] if rows is None else rows)
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
async def test_writer_emits_one_idempotent_mentions_statement():
    repo, session = _repo_capturing()

    written = await repo.write_persona_provenance("Alice", "ds1", ["node-7", "node-9"])

    session.run.assert_awaited_once()
    cypher = session.run.await_args.args[0]
    assert "UNWIND $chunk_ids AS cid" in cypher
    assert "MATCH (c:__Node__ {id: cid})" in cypher
    # The Persona MERGE keys must match SocietyMemory.commit_round exactly.
    assert "MERGE (p:Persona {name: $name, dataset_id: $dataset_id})" in cypher
    assert "MERGE (p)-[:MENTIONS]->(c)" in cypher  # idempotent: MERGE, not CREATE
    assert session.run.await_args.kwargs == {
        "chunk_ids": ["node-7", "node-9"], "name": "Alice", "dataset_id": "ds1",
    }
    assert written == 2


@pytest.mark.asyncio
async def test_writer_strips_dedupes_and_caps_the_batch():
    repo, session = _repo_capturing()

    ids = ["node-7", " node-7 ", "", "   ", "node-9"] + [f"node-{i}" for i in range(10, 40)]
    await repo.write_persona_provenance("Alice", "ds1", ids)

    sent = session.run.await_args.kwargs["chunk_ids"]
    assert sent[:2] == ["node-7", "node-9"]  # stripped, deduped, input order kept
    assert len(sent) == PersonaRepository._PROVENANCE_CHUNK_CAP  # capped


@pytest.mark.asyncio
async def test_writer_empty_input_makes_no_query():
    repo, session = _repo_capturing()

    assert await repo.write_persona_provenance("Alice", "ds1", []) == 0
    assert await repo.write_persona_provenance("Alice", "ds1", ["", "   "]) == 0

    session.run.assert_not_awaited()


@pytest.mark.asyncio
async def test_writer_returns_the_edges_ensured_and_tolerates_unmatched_ids():
    """`count(*)` counts only ids that matched a chunk node — a stale id is skipped."""
    repo, _ = _repo_capturing(rows=[{"written": 1}])
    assert await repo.write_persona_provenance("Alice", "ds1", ["node-7", "stale"]) == 1

    repo, _ = _repo_capturing(rows=[])
    assert await repo.write_persona_provenance("Alice", "ds1", ["node-7"]) == 0


@pytest.mark.asyncio
async def test_get_provenance_returns_the_real_chunk_ids_the_writer_links():
    """The seam: the read path resolves the linked chunk node's own `chunk_id`."""
    repo, _ = _repo_capturing(rows=[{
        "doc_id": "doc:report",
        "title": "Report",
        "breadcrumb": "a > b",
        "chunk_id": CHUNK_UUID,
    }])

    links = await repo.get_provenance("Alice")

    assert [link.chunk_id for link in links] == [UUID(CHUNK_UUID)]
    assert links[0].doc_id == "doc:report"
    assert links[0].title == "Report"
