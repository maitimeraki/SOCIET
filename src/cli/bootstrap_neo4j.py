"""
CLI: apply the Neo4j schema bootstrap (constraints + indexes + vector index).

Usage:
    python -m src.cli.bootstrap_neo4j

Reads connection settings from .env via GraphConfig.
Idempotent — safe to re-run.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from neo4j import AsyncGraphDatabase

from src.graph.config_graph import GraphConfig
from src.graph.neo4j_bootstrap import ensure_schema


async def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    logger = logging.getLogger("bootstrap_neo4j")

    cfg = GraphConfig()
    driver = AsyncGraphDatabase.driver(cfg.neo4j_uri, auth=(cfg.neo4j_username, cfg.neo4j_password))

    try:
        result = await ensure_schema(driver, cfg.neo4j_database)
        applied = result["applied"]
        failed = result["failed"]

        logger.info("Applied %d statements", len(applied))
        for label in applied:
            logger.info("  ✓ %s", label)
        for label, err in failed:
            logger.error("  ✗ %s — %s", label, err)

        return 0 if not failed else 1
    finally:
        await driver.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
