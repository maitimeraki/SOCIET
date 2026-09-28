import os
import pytest
import asyncio
from dotenv import load_dotenv
load_dotenv()
import pytest_asyncio

from src.persona.repository import PersonaRepository



@pytest_asyncio.fixture
async def repo():
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    pwd = os.getenv("NEO4J_PASSWORD", "password")
    db = os.getenv("NEO4J_DATABASE", "neo4j")

    repo = PersonaRepository(neo4j_uri=uri, neo4j_user=user, neo4j_password=pwd, neo4j_database=db)

    # quick healthcheck; if it fails, skip the tests
    try:
        async with repo._driver.session(database=db) as session:
            await session.run("RETURN 1")
    except Exception as e:
        await repo.close()
        pytest.skip(f"Neo4j not available at {uri}: {e}")

    yield repo

    # cleanup nodes created by tests
    try:
        async with repo._driver.session(database=db) as session:
            await session.run("MATCH (n:Persona) WHERE n._test = true DETACH DELETE n")
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_search_agents_by_query_matches_properties(repo):
    # seed test nodes
    async with repo._driver.session(database=repo._db) as session:
        await session.run(
            """
            CREATE (p:Persona {name: $name, title: $title, summary: $summary, domain_tags: $tags, description: $desc, _test: true})
            """,
            name="Infra Strategist",
            title="Cloud Infra Risks",
            summary="Focuses on resilient multi-cloud architecture to reduce outage risk.",
            tags="infrastructure, cloud",
            desc="Resilience-focused infra strategist",
        )

        await session.run(
            """
            CREATE (p:Persona {name: $name, title: $title, summary: $summary, domain_tags: $tags, description: $desc, _test: true})
            """,
            name="Data Analyst",
            title="Market Trends Analysis",
            summary="Analyzes market signals and forecasts trends.",
            tags="economics, markets",
            desc="Analyst focused on signals",
        )

    # test token matching across title / summary / tags
    tokens = ["cloud", "resilient"]
    rows = await repo.search_agents_by_query(archetype_label="Persona", query_tokens=tokens, limit=50)
    names = [r.get("name") for r in rows if r.get("name")]

    assert "Infra Strategist" in names
    assert "Data Analyst" not in names
