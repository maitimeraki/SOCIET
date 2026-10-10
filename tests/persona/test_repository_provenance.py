"""D2: the provenance writer — real `(Persona)-[:MENTIONS]->(Chunk)` edges.

The read path (`get_provenance`) already exists; these tests pin the write
statement, its bounds, and the seam where the two meet (chunk node ids in,
real `chunk.chunk_id`s out). No live Neo4j: the driver is stubbed.
"""
from uuid import UUID
import os
import uuid

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from src.persona.repository import PersonaRepository
from src.persona.agent import ProvenanceLink

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
    repo, session = _repo_capturing(rows=[{
        "doc_id": "doc:report",
        "title": "Report",
        "breadcrumb": "a > b",
        "chunk_id": CHUNK_UUID,
    }])

    links = await repo.get_provenance("Alice")

    assert [link.chunk_id for link in links] == [UUID(CHUNK_UUID)]
    assert links[0].doc_id == "doc:report"
    assert links[0].title == "Report"


@pytest.mark.asyncio
async def test_get_provenance_reads_the_writer_shape():
    """The reader keys on the property the WRITER actually sets.

    `graph_build` carries the source-document id on `document_anchor` (llama-index
    clobbers `document_id`/`doc_id` to the sentinel `"None"`), so the reader must
    read `document_anchor` — reading `doc_id` would return a fabricated id.
    """
    repo, session = _repo_capturing(rows=[])

    await repo.get_provenance("Alice", dataset_id="ds1")

    cypher = session.run.await_args.args[0]
    assert "chunk.document_anchor AS doc_id" in cypher
    assert "chunk.doc_id" not in cypher           # never the sentinel property
    assert "chunk.document_anchor IS NOT NULL" in cypher  # real chunks only
    assert "a.dataset_id = $dataset_id" in cypher  # scoped to the writer's key
    assert session.run.await_args.kwargs["dataset_id"] == "ds1"


@pytest.mark.asyncio
async def test_get_provenance_empty_when_only_unwired_chunks_exist():
    """No real `document_anchor` → no rows → `[]` (the caller's sector fallback run)."""
    repo, _ = _repo_capturing(rows=[])

    assert await repo.get_provenance("Alice", dataset_id="ds1") == []


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
        "chunk_ids": ["node-7", "node-9"], "name": "Alice", "dataset_id": "ds1",
        "stance": None,
    }
    assert linked == 3


@pytest.mark.asyncio
async def test_entity_writer_strips_dedupes_and_caps_the_batch():
    repo, session = _repo_capturing(rows=[{"linked": 1}])

    ids = ["node-7", " node-7 ", "", "   ", "node-9"] + [f"node-{i}" for i in range(10, 40)]
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


# ---- The sector fallback must never reach `summary_provenance` ----
#
# The fallback exists only to give the graph snapshot a stable version/chunk
# count; a persona with no real chunks must expose NO source links, so the turn
# prompt, the verdict, and the frontend never render a fabricated `sector:` id.


def _build_repo(provenance):
    repo = PersonaRepository.__new__(PersonaRepository)
    repo.get_provenance = AsyncMock(return_value=provenance)
    return repo


def _sector_results():
    return [{
        "domain_tag": "education", "total_relevance": 1.0,
        "evidence_nodes": ["Lead"], "density": 1,
    }]


async def _build(repo, sector_results):
    return await repo.build_single_agent_profile_from_node(
        agent_name="Lead",
        node={"name": "Lead", "domain_tags": ["resume"]},
        user_query="how is my resume?",
        dataset_id="ds",
        agent_metrics={"matched_sectors": ["education"]},
        sector_results=sector_results,
        llm_output=None,
    )


@pytest.mark.asyncio
async def test_build_keeps_synthetic_links_out_of_summary_provenance():
    repo = _build_repo([])

    agent = await _build(repo, _sector_results())

    assert agent.summary_provenance == []                      # honest: no sources
    # …but the fallback still feeds the graph snapshot (behaviour preserved).
    assert agent.graph_snapshot.chunk_count == 1


@pytest.mark.asyncio
async def test_build_keeps_real_provenance_in_summary_provenance():
    real = ProvenanceLink(
        doc_id="DOC-1", title="Report", breadcrumb="a > b", chunk_id=UUID(CHUNK_UUID),
    )
    repo = _build_repo([real])

    agent = await _build(repo, _sector_results())

    assert [p.doc_id for p in agent.summary_provenance] == ["DOC-1"]


# ---- Live: the reader recovers REAL provenance from a writer-shaped chunk ----
#
# The central FIX-1 claim: a persona wired to a real chunk reads that chunk's
# source document, not the fabricated `sector:` fallback. Decided by the real
# query against a seeded graph, not a substring — mirrors the live tests in
# tests/simulation/test_snapshot_fidelity.py.


@pytest_asyncio.fixture
async def live_repo():
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USERNAME", os.getenv("NEO4J_USER", "neo4j"))
    pwd = os.getenv("NEO4J_PASSWORD", "password")
    db = os.getenv("NEO4J_DATABASE", "neo4j")

    repo = PersonaRepository(
        neo4j_uri=uri, neo4j_user=user, neo4j_password=pwd, neo4j_database=db,
    )
    try:
        async with repo._driver.session(database=db) as session:
            await session.run("RETURN 1")
    except Exception as exc:
        await repo.close()
        pytest.skip(f"Neo4j not available at {uri}: {exc}")

    yield repo, repo._driver, db
    await repo.close()


@pytest.mark.asyncio
async def test_get_provenance_reads_real_document_id_on_the_live_graph(live_repo):
    """A chunk carrying `document_anchor` yields the REAL doc id, not `"None"`/sector."""
    repo, driver, db = live_repo
    ds = f"itest-prov-{uuid.uuid4().hex[:10]}"
    cid = f"chunk-{uuid.uuid4().hex[:10]}"
    doc_anchor = f"DOC-{uuid.uuid4().hex[:8]}"

    try:
        async with driver.session(database=db) as session:
            await session.run(
                """
                MERGE (p:Persona {name: 'itest-Prov', dataset_id: $ds})
                MERGE (c:__Node__ {id: $cid})
                SET c:Chunk, c.text = 'chunk body', c.dataset_id = $ds,
                    c.document_anchor = $anchor,
                    c.title = 'EU Market 2027', c.breadcrumb = 'Section 3 > Risks',
                    c.chunk_id = $chunk_id,
                    c.doc_id = 'None'  // the sentinel llama-index writes
                MERGE (p)-[:MENTIONS]->(c)
                """,
                ds=ds, cid=cid, anchor=doc_anchor, chunk_id=CHUNK_UUID,
            )

        links = await repo.get_provenance("itest-Prov", dataset_id=ds)

        assert [link.doc_id for link in links] == [doc_anchor]      # real, not "None"
        assert links[0].title == "EU Market 2027"
        assert links[0].breadcrumb == "Section 3 > Risks"
        assert links[0].chunk_id == UUID(CHUNK_UUID)

        # A persona with no wired chunks reads empty — never a fabricated link.
        assert await repo.get_provenance("itest-Prov", dataset_id="other-ds") == []
    finally:
        async with driver.session(database=db) as session:
            await session.run("MATCH (n) WHERE n.dataset_id = $ds DETACH DELETE n", ds=ds)
