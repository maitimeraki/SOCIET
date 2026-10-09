"""Task 6: pairing must bias toward disagreeing stances, not comfort.

The mocked topology tests assert Cypher text only, so the *ordering* the task
is defined by -- two agents with shared entities but opposed stances scoring
strictly higher than the same-stance pair at equal Jaccard -- is proven here
against the real graph. Skipped when Neo4j is unreachable; everything seeded is
cleaned up by its unique dataset id.
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from dotenv import load_dotenv

from src.persona.repository import PersonaRepository
from src.simulation.debate_config import DebateConfig
from src.simulation.topology import CommunicationTopology, _STANCE_DIVERGENCE_BONUS

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

    yield repo, db
    await repo.close()


async def _seed_shared_entity(repo, db, ds, entity):
    """One chunk mentioning one entity, so every persona linked to it shares it."""
    chunk_id = f"itest-stance-chunk-{uuid4().hex[:10]}"
    async with repo._driver.session(database=db) as session:
        await session.run(
            """
            CREATE (c:__Node__:Chunk {id: $chunk_id, chunk_id: $chunk_id,
                    doc_id: $chunk_id, dataset_id: $ds, title: 'itest',
                    breadcrumb: '', _test: true})
            CREATE (e:__Node__:__Entity__ {id: $entity, name: $entity,
                    dataset_id: $ds, triplet_source_id: $chunk_id, _test: true})
            CREATE (c)-[:MENTIONS]->(e)
            """,
            chunk_id=chunk_id, ds=ds, entity=entity,
        )
    return chunk_id


def _roster(*names):
    return [
        SimpleNamespace(identity=SimpleNamespace(name=n), communication_radius=1)
        for n in names
    ]


def _score_for(pairs, a, b):
    for p in pairs:
        if {p.agent_a, p.agent_b} == {a, b}:
            return p.score
    raise AssertionError(f"no pair for {a}/{b} in {[(p.agent_a, p.agent_b) for p in pairs]}")


@pytest.mark.asyncio
@pytest.mark.parametrize("round_num", [1, 2])
async def test_opposed_stance_pairs_outscore_same_stance_at_equal_jaccard(live, round_num):
    """Definition of done: opposed (POSITIVE/NEGATIVE) > same (POSITIVE/POSITIVE),
    at equal Jaccard, in BOTH the round-1 and round-2+ Cypher bodies."""
    repo, db = live
    ds = f"itest-stance-{uuid4().hex[:10]}"
    entity = f"itest-stance-entity-{uuid4().hex[:8]}"
    # A/B opposed; C/D same-stance. Round 2 reads current_stance, so seed both.
    stances = {"itest-A": "POSITIVE", "itest-B": "NEGATIVE",
               "itest-C": "POSITIVE", "itest-D": "POSITIVE"}

    try:
        chunk_id = await _seed_shared_entity(repo, db, ds, entity)
        for name, stance in stances.items():
            await repo.write_persona_entity_links(name, ds, [chunk_id], stance=stance)
        async with repo._driver.session(database=db) as session:
            await session.run(
                "MATCH (p:Persona) WHERE p.dataset_id = $ds AND p.name IN $names "
                "SET p.current_stance = p.stance",
                ds=ds, names=list(stances),
            )

        topology = CommunicationTopology(repo._driver, db)
        pairs = await topology.compute_round_pairs(
            _roster(*stances), dataset_id=ds, round_num=round_num,
            config=DebateConfig(comm_radius=1),
        )

        opposed = _score_for(pairs, "itest-A", "itest-B")
        same = _score_for(pairs, "itest-C", "itest-D")
        assert opposed > same, f"round {round_num}: opposed {opposed} !> same {same}"
    finally:
        async with repo._driver.session(database=db) as session:
            await session.run("MATCH (n) WHERE n.dataset_id = $ds DETACH DELETE n", ds=ds)


@pytest.mark.asyncio
@pytest.mark.parametrize("round_num", [1, 2])
async def test_missing_stance_adds_no_bonus_and_does_not_break_the_query(live, round_num):
    """Legacy personas carry no stance: the divergence term must be 0 (not an
    error), so existing pairings are unchanged when Task 1 has not run."""
    repo, db = live
    ds = f"itest-stance-legacy-{uuid4().hex[:10]}"
    entity = f"itest-legacy-entity-{uuid4().hex[:8]}"
    # N1/N2 legacy (no stance at all); M1 has a stance -> half-present, still 0.
    stances = {"itest-N1": None, "itest-N2": None, "itest-M1": "POSITIVE"}

    try:
        chunk_id = await _seed_shared_entity(repo, db, ds, entity)
        for name, stance in stances.items():
            await repo.write_persona_entity_links(name, ds, [chunk_id], stance=stance)

        topology = CommunicationTopology(repo._driver, db)
        pairs = await topology.compute_round_pairs(
            _roster(*stances), dataset_id=ds, round_num=round_num,
            config=DebateConfig(comm_radius=1),
        )

        # Both stance-less -> plain Jaccard (1.0), no divergence bonus.
        assert _score_for(pairs, "itest-N1", "itest-N2") == pytest.approx(1.0)
        # One stance-less -> still no bonus.
        assert _score_for(pairs, "itest-M1", "itest-N1") == pytest.approx(1.0)
    finally:
        async with repo._driver.session(database=db) as session:
            await session.run("MATCH (n) WHERE n.dataset_id = $ds DETACH DELETE n", ds=ds)


def test_both_pair_cyphers_carry_the_guarded_divergence_term():
    """Fast check (no Neo4j): round 1 reads `Persona.stance`, round 2+ reads
    `Persona.current_stance`, and both guard for absent stances so the term is
    added in BOTH bodies rather than vanishing after round 1."""
    topology = CommunicationTopology(MagicMock(), "db")
    round1, _ = topology._round1_cypher(["A", "B"], "ds", DebateConfig())
    round_n, _ = topology._round_n_cypher(["A", "B"], "ds", DebateConfig(), 2)

    for cypher, stance_prop in ((round1, "a.stance"), (round_n, "a.current_stance")):
        assert stance_prop in cypher
        assert "IS NOT NULL" in cypher
        assert str(_STANCE_DIVERGENCE_BONUS) in cypher
