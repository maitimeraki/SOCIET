"""Live proof that synthesis-written links make topology pairs real.

The mocked topology tests assert Cypher text only, and the mocked synthesizer
tests never execute the writers — so the seam where they meet the real graph
was never tested end to end. This test seeds the real shape (chunk → entity
MENTIONS, llama-index's direction), runs the real `write_persona_entity_links`,
and lets the real round-1 pairing Cypher decide. Skipped when Neo4j is
unreachable; everything seeded is cleaned up by its unique dataset id.
"""
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from dotenv import load_dotenv

from src.persona.graph_context import EntityNode
from src.persona.repository import PersonaRepository
from src.simulation.debate_config import DebateConfig
from src.simulation.profile_synthesizer import ProfileSynthesizer
from src.simulation.topology import CommunicationTopology

load_dotenv()


@pytest_asyncio.fixture
async def live():
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    pwd = os.getenv("NEO4J_PASSWORD", "password")
    db = os.getenv("NEO4J_DATABASE", "neo4j")

    repo = PersonaRepository(
        neo4j_uri=uri, neo4j_user=user, neo4j_password=pwd, neo4j_database=db,
    )
    try:
        async with repo._driver.session(database=db) as session:
            await session.run("RETURN 1")
    except Exception as e:
        await repo.close()
        pytest.skip(f"Neo4j not available at {uri}: {e}")

    yield repo._driver, repo, db
    await repo.close()


@pytest.mark.asyncio
async def test_synthesis_written_entity_links_produce_round1_pairs(live):
    driver, repo, db = live
    ds = f"itest-pairing-{uuid4().hex[:10]}"
    chunk_id = f"itest-chunk-{uuid4().hex[:10]}"
    doc_id = f"itest-doc-{uuid4().hex[:10]}"
    entity_names = ["itest-entity-alpha", "itest-entity-beta", "itest-entity-gamma"]
    agent_a, agent_b = "itest-agent-a", "itest-agent-b"
    topology = CommunicationTopology(driver, db)

    def roster():
        return [
            SimpleNamespace(identity=SimpleNamespace(name=agent_a), communication_radius=1),
            SimpleNamespace(identity=SimpleNamespace(name=agent_b), communication_radius=1),
        ]

    try:
        async with driver.session(database=db) as session:
            await session.run(
                """
                CREATE (c:__Node__:Chunk {id: $chunk_id, chunk_id: $chunk_id, doc_id: $doc_id,
                        dataset_id: $ds, title: 'itest', breadcrumb: '', _test: true})
                WITH c
                UNWIND $names AS name
                CREATE (e:__Node__:__Entity__ {id: name, name: name, dataset_id: $ds,
                        triplet_source_id: $chunk_id, _test: true})
                CREATE (c)-[:MENTIONS]->(e)
                """,
                chunk_id=chunk_id, doc_id=doc_id, ds=ds, names=entity_names,
            )

        # No persona edges yet: round 1 can pair nobody.
        before = await topology.compute_round_pairs(
            roster(), dataset_id=ds, round_num=1, config=DebateConfig(),
        )
        assert before == []

        written = await repo.write_persona_entity_links(agent_a, ds, [chunk_id])
        await repo.write_persona_entity_links(agent_b, ds, [chunk_id])
        assert written == len(entity_names)

        async with driver.session(database=db) as session:
            result = await session.run(
                "MATCH (p:Persona {name: $name, dataset_id: $ds}) "
                "RETURN p.domain_tags AS tags, p.entity_affinity AS affinity",
                name=agent_a, ds=ds,
            )
            row = await result.single()
        assert row is not None
        assert sorted(row["tags"]) == sorted(entity_names)
        assert sorted(row["affinity"]) == sorted(entity_names)

        pairs = await topology.compute_round_pairs(
            roster(), dataset_id=ds, round_num=1, config=DebateConfig(),
        )
        assert len(pairs) == 1
        assert {pairs[0].agent_a, pairs[0].agent_b} == {agent_a, agent_b}
        assert sorted(pairs[0].shared_entities) == sorted(entity_names)
        assert pairs[0].score >= DebateConfig().topology_score_threshold
    finally:
        async with driver.session(database=db) as session:
            await session.run(
                "MATCH (n) WHERE n.dataset_id = $ds DETACH DELETE n", ds=ds,
            )


@pytest.mark.asyncio
async def test_single_cell_graph_synthesizes_a_debatable_roster(live):
    """The reported bug's shape, end to end: one chunk, one document, N entities.

    Synthesis must derive one persona per required node (never one collapsed
    persona), write the links, and let the real round-1 Cypher pair them.
    """
    driver, repo, db = live
    ds = f"itest-roster-{uuid4().hex[:10]}"
    chunk_id = f"itest-chunk-{uuid4().hex[:10]}"
    doc_id = f"itest-doc-{uuid4().hex[:10]}"
    names = ["itest-roster-alpha", "itest-roster-beta", "itest-roster-gamma"]
    topology = CommunicationTopology(driver, db)

    try:
        async with driver.session(database=db) as session:
            await session.run(
                """
                CREATE (c:__Node__:Chunk {id: $chunk_id, chunk_id: $chunk_id, doc_id: $doc_id,
                        dataset_id: $ds, title: 'itest', breadcrumb: '', _test: true})
                WITH c
                UNWIND $names AS name
                CREATE (e:__Node__:__Entity__ {id: name, name: name, dataset_id: $ds,
                        triplet_source_id: $chunk_id, _test: true})
                CREATE (c)-[:MENTIONS]->(e)
                """,
                chunk_id=chunk_id, doc_id=doc_id, ds=ds, names=names,
            )

        # The vector entry is stubbed (no embeddings in a unit run); everything
        # else is real: node-level derivation, the real writers, the real
        # round-1 pairing Cypher.
        class _SeededContext:
            async def find_relevant_entities(self, query, limit=10):
                return [
                    EntityNode(
                        id=name, name=name, label="Entity",
                        properties={"name": name, "triplet_source_id": chunk_id},
                        relevance_score=0.9 - index * 0.1,
                    )
                    for index, name in enumerate(names)
                ]

        async def _stub_build(**kwargs):
            return SimpleNamespace(identity=SimpleNamespace(name=kwargs["agent_name"]))

        repo.calculate_agent_metrics_and_context_for_llm = AsyncMock(return_value={})
        repo.build_single_agent_profile_from_node = AsyncMock(side_effect=_stub_build)
        synth = ProfileSynthesizer(persona_repo=repo, graph_context=_SeededContext())

        profiles = await synth.synthesize(query="q", dataset_id=ds, max_agents=10)

        assert sorted(p.identity.name for p in profiles) == sorted(names)

        roster = [
            SimpleNamespace(identity=SimpleNamespace(name=p.identity.name), communication_radius=1)
            for p in profiles
        ]
        pairs = await topology.compute_round_pairs(
            roster, dataset_id=ds, round_num=1, config=DebateConfig(),
        )
        assert len(pairs) == 3  # every unordered pair of the three personas
        assert all(p.score >= DebateConfig().topology_score_threshold for p in pairs)
    finally:
        async with driver.session(database=db) as session:
            await session.run("MATCH (n) WHERE n.dataset_id = $ds DETACH DELETE n", ds=ds)
