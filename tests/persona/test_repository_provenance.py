"""D2: the provenance writer — real `(Persona)-[:MENTIONS]->(Chunk)` edges.

The read path lives in `GraphContext.get_provenance`; these tests pin the write
statement, its bounds, and the seam where the two meet (chunk node ids in,
real `chunk.chunk_id`s out). No live Neo4j: the driver is stubbed.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.graph.scope import chunk_in_dataset, entity_in_dataset
from src.persona.repository import PersonaRepository

CHUNK_UUID = "3f1d2c9a-0000-4000-8000-000000000001"


def _repo_on(recorder) -> PersonaRepository:
    repo = PersonaRepository.__new__(PersonaRepository)
    repo._driver = recorder.driver
    repo._db = "testdb"
    return repo


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
        "chunk_ids": ["node-7", "node-9"],
        "name": "Alice",
        "dataset_id": "ds1",
    }
    assert written == 2


@pytest.mark.asyncio
async def test_writer_strips_dedupes_and_caps_the_batch():
    repo, session = _repo_capturing()

    ids = ["node-7", " node-7 ", "", "   ", "node-9"] + [
        f"node-{i}" for i in range(10, 40)
    ]
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


# ---- Entity links: the `(Persona)-[:MENTIONS]->(__Entity__)` edges topology counts ----


@pytest.mark.asyncio
async def test_entity_writer_emits_one_idempotent_mentions_statement():
    """Topology pair scoring counts shared non-Chunk middles; this write creates them."""
    repo, session = _repo_capturing(rows=[{"linked": 3}])

    linked = await repo.write_persona_entity_links("Alice", "ds1", ["node-7", "node-9"])

    session.run.assert_awaited_once()
    cypher = session.run.await_args.args[0]
    assert "UNWIND $chunk_ids AS cid" in cypher
    assert "MATCH (c:__Node__ {id: cid})-[:MENTIONS]->(e:__Entity__)" in cypher
    # The Persona MERGE keys must match SocietyMemory.commit_round exactly.
    assert "MERGE (p:Persona {name: $name, dataset_id: $dataset_id})" in cypher
    assert "MERGE (p)-[:MENTIONS]->(e)" in cypher  # idempotent: MERGE, not CREATE
    assert "SET p.domain_tags = names, p.entity_affinity = names" in cypher
    assert "p.stance = coalesce($stance, p.stance)" in cypher
    assert session.run.await_args.kwargs == {
        "chunk_ids": ["node-7", "node-9"],
        "name": "Alice",
        "dataset_id": "ds1",
        "stance": None,
    }
    assert linked == 3


@pytest.mark.asyncio
async def test_entity_writer_strips_dedupes_and_caps_the_batch():
    repo, session = _repo_capturing(rows=[{"linked": 1}])

    ids = ["node-7", " node-7 ", "", "   ", "node-9"] + [
        f"node-{i}" for i in range(10, 40)
    ]
    await repo.write_persona_entity_links("Alice", "ds1", ids)

    sent = session.run.await_args.kwargs["chunk_ids"]
    assert sent[:2] == ["node-7", "node-9"]  # stripped, deduped, input order kept
    assert len(sent) == PersonaRepository._PROVENANCE_CHUNK_CAP  # capped


@pytest.mark.asyncio
async def test_entity_writer_empty_input_makes_no_query():
    repo, session = _repo_capturing()

    assert await repo.write_persona_entity_links("Alice", "ds1", []) == 0
    assert await repo.write_persona_entity_links("Alice", "ds1", ["", "   "]) == 0

    session.run.assert_not_awaited()


@pytest.mark.asyncio
async def test_entity_writer_returns_zero_when_no_entity_rows_come_back():
    repo, _ = _repo_capturing(rows=[])

    assert await repo.write_persona_entity_links("Alice", "ds1", ["node-7"]) == 0


# ---- Audit C1: every provenance and evidence read and write is dataset-scoped ----


@pytest.mark.asyncio
async def test_provenance_writer_scopes_the_chunk_to_the_dataset(recorder):
    await _repo_on(recorder).write_persona_provenance("Alice", "ds-A", ["node-7"])

    query, params = recorder.calls[0]
    assert chunk_in_dataset("c") in query
    assert params["dataset_id"] == "ds-A"


@pytest.mark.asyncio
async def test_entity_link_writer_scopes_the_chunk_and_the_entity(recorder):
    await _repo_on(recorder).write_persona_entity_links("Alice", "ds-A", ["node-7"])

    query, params = recorder.calls[0]
    assert chunk_in_dataset("c") in query
    assert entity_in_dataset("e") in query
    assert params["dataset_id"] == "ds-A"
