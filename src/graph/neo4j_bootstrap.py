"""
Neo4j schema bootstrap.

Idempotent CREATE statements for every constraint and index the simulation
pipeline assumes. Run via:

  - CLI:  python -m src.cli.bootstrap_neo4j
  - App:  await ensure_schema(driver, database)   (called from FastAPI lifespan)

Production-grade invariants enforced here:

  1. (Persona {name, dataset_id}) is unique — writeback's MERGE becomes
     a single indexed lookup, not a graph scan.
  2. (Chunk {chunk_id}) is unique — provenance lookups are O(log n).
  3. Vector indexes `persona_embeddings` (Persona.embedding) and
     `entity_embeddings` (`__Entity__.embedding`, llama-index store shape) —
     vector retrieval never hits "no such index".
  4. Lookup indexes for chunk.doc_id, agent.updated_at — hot read paths
     become O(log n) instead of full scans.

`show_progress=False` is intentional; CREATE (IF NOT EXISTS) on a populated
DB returns instantly and we want this silent in production logs.
"""
from __future__ import annotations

import logging
from typing import Optional

from neo4j import AsyncGraphDatabase

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema statements
# ---------------------------------------------------------------------------

# Vector index parameters — must match the embed model in production.
# Default OllamaEmbeddings("nomic-embed-text:v1.5") produces 768-dim vectors.
EMBEDDING_DIMENSIONS = 768
EMBEDDING_SIMILARITY = "cosine"


def _statements() -> list[tuple[str, dict]]:
    """All schema statements, in dependency order.

    Tuple shape: (cypher_template, params_for_substitution).
    """
    return [
        # ---- Uniqueness constraints ----
        (
            "CREATE CONSTRAINT persona_name_dataset IF NOT EXISTS "
            "FOR (p:Persona) REQUIRE (p.name, p.dataset_id) IS UNIQUE",
            {},
        ),
        (
            "CREATE CONSTRAINT chunk_id IF NOT EXISTS "
            "FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE",
            {},
        ),
        (
            "CREATE CONSTRAINT agent_id IF NOT EXISTS "
            "FOR (a:Agent) REQUIRE a.id IS UNIQUE",
            {},
        ),
        # ---- Lookup indexes ----
        (
            "CREATE INDEX chunk_doc_dataset IF NOT EXISTS "
            "FOR (c:Chunk) ON (c.doc_id, c.dataset_id)",
            {},
        ),
        (
            "CREATE INDEX persona_dataset IF NOT EXISTS "
            "FOR (p:Persona) ON (p.dataset_id)",
            {},
        ),
        (
            "CREATE INDEX agent_archetype IF NOT EXISTS "
            "FOR (a:Agent) ON (a.archetype)",
            {},
        ),
        (
            "CREATE INDEX agent_updated IF NOT EXISTS "
            "FOR (a:Agent) ON (a.updated_at)",
            {},
        ),
        # ---- Vector index (entity embeddings; llama-index store writes __Entity__) ----
        (
            "CREATE VECTOR INDEX entity_embeddings IF NOT EXISTS "
            "FOR (n:__Entity__) ON (n.embedding) "
            "OPTIONS { "
            "  indexConfig: { "
            "    `vector.dimensions`: $dimensions, "
            "    `vector.similarity_function`: $similarity "
            "  } "
            "}",
            {"dimensions": EMBEDDING_DIMENSIONS, "similarity": EMBEDDING_SIMILARITY},
        ),
        # ---- Vector index (Persona.embedding) ----
        (
            "CREATE VECTOR INDEX persona_embeddings IF NOT EXISTS "
            "FOR (n:Persona) ON (n.embedding) "
            "OPTIONS { "
            "  indexConfig: { "
            "    `vector.dimensions`: $dimensions, "
            "    `vector.similarity_function`: $similarity "
            "  } "
            "}",
            {"dimensions": EMBEDDING_DIMENSIONS, "similarity": EMBEDDING_SIMILARITY},
        ),
    ]


# ---------------------------------------------------------------------------
# Bootstrap entry points
# ---------------------------------------------------------------------------


async def ensure_schema(
    driver: AsyncGraphDatabase.driver,
    database: str,
) -> dict:
    """Apply every schema statement. Idempotent.

    Returns a dict summarizing what was applied vs. what already existed
    (Neo4j returns the count for IF NOT EXISTS clauses; we record success
    rather than parsed counts, since IF NOT EXISTS doesn't surface that
    distinction).
    """
    applied: list[str] = []
    failed: list[tuple[str, str]] = []

    async with driver.session(database=database) as session:
        for cypher, params in _statements():
            label = _statement_label(cypher)
            try:
                await session.run(cypher, **params)
                applied.append(label)
                logger.debug("Schema applied: %s", label)
            except Exception as exc:  # pragma: no cover — defensive
                failed.append((label, str(exc)))
                logger.exception("Failed to apply schema statement: %s", label)

    if failed:
        logger.warning(
            "Schema bootstrap completed with %d failures (of %d total)",
            len(failed),
            len(applied) + len(failed),
        )

    return {"applied": applied, "failed": failed}


def _statement_label(cypher: str) -> str:
    """Best-effort human label for log lines."""
    for kw in (
        "CONSTRAINT persona_name_dataset",
        "CONSTRAINT chunk_id",
        "CONSTRAINT agent_id",
        "INDEX chunk_doc_dataset",
        "INDEX persona_dataset",
        "INDEX agent_archetype",
        "INDEX agent_updated",
        "VECTOR INDEX persona_embeddings",
        "VECTOR INDEX entity_embeddings",
    ):
        if kw in cypher:
            return kw
    return "unknown"


# ---------------------------------------------------------------------------
# Self-check (run as a module for verification)
# ---------------------------------------------------------------------------


async def _selftest(uri: str, user: str, password: str, database: str) -> None:
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    try:
        result = await ensure_schema(driver, database)
        logger.info("Bootstrap result: %s", result)
    finally:
        await driver.close()


if __name__ == "__main__":  # pragma: no cover
    import asyncio

    from src.graph.config_graph import GraphConfig

    cfg = GraphConfig()
    asyncio.run(_selftest(cfg.neo4j_uri, cfg.neo4j_username, cfg.neo4j_password, cfg.neo4j_database))
