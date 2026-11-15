"""The roster → evidence → stance → pairing chain, on a writer-shaped graph.

Tasks 1/2/6/8 all rest on one assumption: a real ingested graph carries
`:__Node__:Chunk` nodes whose `id` is the entity's `triplet_source_id`. Every
other "live" test seeds a convenient fixture, so this seeds the EXACT shape
`graph_build`/llama-index write and drives the REAL
`ProfileSynthesizer.synthesize` roster path over it — the entity's node
properties are read back out of the graph and handed to the synthesizer the way
a real `GraphContext.find_relevant_entities` would, so nothing about the chain
is assumed by the fixture. Skipped when Neo4j is unreachable; everything seeded
is cleaned up by its unique dataset id.
"""

import os
from uuid import uuid4

import pytest
import pytest_asyncio
from dotenv import load_dotenv

from src.persona.graph_context import ChunkHit, ChunkSearch, EntityNode
from src.persona.repository import PersonaRepository
from src.simulation.debate_config import DebateConfig
from src.simulation.profile_synthesizer import ProfileSynthesizer
from src.simulation.topology import _STANCE_DIVERGENCE_BONUS, CommunicationTopology

load_dotenv()

CHUNK_TEXT = "The EU market entry carries a 4.2% regulatory surcharge."


class _StubCtx:
    """The reads the roster path makes, with no embeddings and no LLM.

    `find_relevant_entities` returns EntityNodes whose `properties` are the
    seeded graph nodes' own properties (the test reads them back), so the
    synthesizer consumes exactly what a real GraphContext would surface. The
    chunk legs name the entities the way the seeded chunks MENTION them: one
    `(chunk_id, entity_ids)` pair per seeded chunk, in rank order.
    """

    def __init__(self, nodes, chunk_mentions):
        self._nodes = list(nodes)
        self._mentions = list(chunk_mentions)

    async def find_relevant_entities(self, query, dataset_id, limit):
        return list(self._nodes)

    async def find_relevant_chunks(self, query, dataset_id, limit=200):
        hits = [
            ChunkHit(
                chunk_id=chunk_id,
                doc_id=f"doc-{chunk_id}",
                doc_title="",
                section="",
                text="",
                rank=rank,
                entity_ids=tuple(entity_ids),
            )
            for rank, (chunk_id, entity_ids) in enumerate(self._mentions, start=1)
        ]
        return ChunkSearch(vector=hits, fulltext=hits)

    async def find_entities_by_ids(self, entity_ids, dataset_id):
        return []

    async def find_connected_nodes_by_seed(self, node_ids, dataset_id, limit=10):
        return {}


@pytest_asyncio.fixture
async def live():
    uri = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
    user = os.getenv("NEO4J_USERNAME", os.getenv("NEO4J_USER", "neo4j"))
    pwd = os.getenv("NEO4J_PASSWORD", "password")
    db = os.getenv("NEO4J_DATABASE", "neo4j")

    repo = PersonaRepository(
        neo4j_uri=uri,
        neo4j_user=user,
        neo4j_password=pwd,
        neo4j_database=db,
    )
    try:
        async with repo._driver.session(database=db) as session:
            await session.run("RETURN 1")
    except Exception as exc:
        await repo.close()
        pytest.skip(f"Neo4j not available at {uri}: {exc}")

    yield repo, db
    await repo.close()


async def _seed_writer_shaped_graph(repo, db, ds):
    """One chunk + two entities in the exact shape `graph_build` writes.

    The chunk carries every property the reader keys on (`id`, `text`,
    `document_anchor`, `title`, `breadcrumb`, `chunk_id`, `dataset_id`); each
    sourced entity points back at it via `triplet_source_id`. A third entity
    has NO `triplet_source_id` — the legacy/unsourced case. Returns the chunk
    node id, the document anchor, and the three entity names.
    """
    suffix = uuid4().hex[:8]
    chunk_id = f"itest-roster-chunk-{suffix}"
    chunk2_id = f"itest-roster-chunk2-{suffix}"
    doc_anchor = f"DOC-{suffix}"
    names = (f"itest-adv-{suffix}", f"itest-skep-{suffix}", f"itest-legacy-{suffix}")

    async with repo._driver.session(database=db) as session:
        await session.run(
            """
            CREATE (c:__Node__:Chunk {
                id: $chunk_id, text: $text, document_anchor: $anchor,
                title: 'EU Market 2027', breadcrumb: 'Section 3 > Risks',
                chunk_id: $chunk_uuid, dataset_id: $ds})
            CREATE (adv:__Node__:__Entity__ {
                id: 'ent-adv', name: $adv, triplet_source_id: $chunk_id,
                stance: 'POSITIVE', domain_tags: ['trade'], dataset_id: $ds})
            CREATE (skep:__Node__:__Entity__ {
                id: 'ent-skep', name: $skep, triplet_source_id: $chunk_id,
                stance: 'NEGATIVE', domain_tags: ['trade'], dataset_id: $ds})
            CREATE (legacy:__Node__:__Entity__ {
                id: 'ent-legacy', name: $legacy,
                stance: 'NEUTRAL', domain_tags: ['trade'], dataset_id: $ds})
            CREATE (c)-[:MENTIONS]->(adv)
            CREATE (c)-[:MENTIONS]->(skep)
            CREATE (c2:__Node__:Chunk {
                id: $chunk2_id, text: $text, document_anchor: $anchor,
                title: 'EU Market 2027', breadcrumb: 'Section 4 > Entry',
                chunk_id: $chunk2_uuid, dataset_id: $ds})
            CREATE (c2)-[:MENTIONS]->(adv)
            CREATE (c2)-[:MENTIONS]->(skep)
            CREATE (d:Document {dataset_id: $ds, _test: true})
            CREATE (adv)-[:DERIVED_FROM]->(d)
            CREATE (skep)-[:DERIVED_FROM]->(d)
            CREATE (legacy)-[:DERIVED_FROM]->(d)
            """,
            chunk_id=chunk_id,
            text=CHUNK_TEXT,
            anchor=doc_anchor,
            chunk_uuid=str(uuid4()),
            chunk2_id=chunk2_id,
            chunk2_uuid=str(uuid4()),
            ds=ds,
            adv=names[0],
            skep=names[1],
            legacy=names[2],
        )
    return chunk_id, chunk2_id, doc_anchor, names


async def _entity_nodes(repo, db, names):
    """EntityNodes built from the seeded nodes' OWN properties — what a real
    `GraphContext.find_relevant_entities` hands the synthesizer."""
    async with repo._driver.session(database=db) as session:
        res = await session.run(
            "MATCH (e:__Entity__) WHERE e.name IN $names "
            "RETURN e.id AS id, e.name AS name, properties(e) AS props",
            names=list(names),
        )
        rows = await res.data()
    return [
        EntityNode(
            id=r["id"],
            name=r["name"],
            label="Entity",
            properties=r["props"],
            relevance_score=1.0,
        )
        for r in rows
    ]


def _score_for(pairs, a, b):
    for p in pairs:
        if {p.agent_a, p.agent_b} == {a, b}:
            return p.score
    raise AssertionError(
        f"no pair for {a}/{b} in {[(p.agent_a, p.agent_b) for p in pairs]}"
    )


@pytest.mark.asyncio
async def test_roster_chain_holds_on_writer_shaped_graph(live):
    repo, db = live
    ds = f"itest-roster-{uuid4().hex[:10]}"
    chunk_id, chunk2_id, doc_anchor, (adv_name, skep_name, legacy_name) = (
        await _seed_writer_shaped_graph(repo, db, ds)
    )

    try:
        nodes = await _entity_nodes(repo, db, (adv_name, skep_name, legacy_name))
        ids = {node.name: node.id for node in nodes}
        mentions = [(chunk_id, [ids[adv_name], ids[skep_name]]), (chunk2_id, [ids[adv_name], ids[skep_name]])]
        synth = ProfileSynthesizer(repo, _StubCtx(nodes, mentions))
        decisions: list = []
        agents = await synth.synthesize(
            query="Should we expand into the EU?",
            dataset_id=ds,
            max_agents=5,
            decisions=decisions,
        )
        by_name = {a.identity.name: a for a in agents}
        assert {adv_name, skep_name} <= set(by_name), by_name.keys()
        assert legacy_name not in by_name
        reasons = {d.name: d.reason for d in decisions}
        assert reasons[legacy_name] == "evidence 0 < 2"
        adv, skep = by_name[adv_name], by_name[skep_name]

        # (1) entity.triplet_source_id == chunk.id, and the `(c:Chunk {id}).text`
        # read holds on writer-shaped data: the seeded text is the evidence, and
        # the provenance the same write wired is the real document, not "None".
        assert [e.text for e in adv.evidence] == [CHUNK_TEXT]
        assert [e.text for e in skep.evidence] == [CHUNK_TEXT]
        assert [e.doc_id for e in adv.evidence] == [doc_anchor]

        # (2) Task 1 Step 9 → Task 6: the derived stance is persisted and
        # readable on the Persona node, and the built Agent agrees (no drift).
        async with repo._driver.session(database=db) as session:
            res = await session.run(
                "MATCH (p:Persona) WHERE p.dataset_id = $ds AND p.name IN $names "
                "RETURN p.name AS name, p.stance AS stance",
                ds=ds,
                names=[adv_name, skep_name],
            )
            persisted = {r["name"]: r["stance"] for r in await res.data()}
        assert persisted[adv_name] == "POSITIVE"
        assert persisted[skep_name] == "NEGATIVE"
        assert adv.stance.value == persisted[adv_name]
        assert skep.stance.value == persisted[skep_name]

        # (3) Round-1 pairing reads that persisted stance: opposed stances score
        # strictly above the bare Jaccard — the divergence term is computable.
        topology = CommunicationTopology(repo._driver, db)
        pairs = await topology.compute_round_pairs(
            agents,
            dataset_id=ds,
            round_num=1,
            config=DebateConfig(comm_radius=1),
        )
        assert _score_for(pairs, adv_name, skep_name) == pytest.approx(
            1.0 + _STANCE_DIVERGENCE_BONUS
        )

        # (4) Negative case: the entity with NO `triplet_source_id` and no chunk
        # mention has no evidence, so it is refused, and no Persona is written.
        async with repo._driver.session(database=db) as session:
            res = await session.run(
                "MATCH (p:Persona {name: $name, dataset_id: $ds}) RETURN count(p) AS personas",
                name=legacy_name,
                ds=ds,
            )
            assert (await res.data())[0]["personas"] == 0
    finally:
        async with repo._driver.session(database=db) as session:
            await session.run(
                "MATCH (n) WHERE n.dataset_id = $ds DETACH DELETE n", ds=ds
            )
