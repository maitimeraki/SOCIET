from neo4j import AsyncGraphDatabase
from .config_graph import GraphConfig


class GraphNormalizationStage:
    def __init__(self, config: GraphConfig):
        self.config = config

    async def run(self, dataset_id: str) -> None:
        try:
            driver = AsyncGraphDatabase.driver(
                self.config.neo4j_uri,
                auth=(self.config.neo4j_username, self.config.neo4j_password),
            )

            async with driver.session(database=self.config.neo4j_database) as session:
                # Canonical key for exact/surface-level normalization
                await session.run(
                    """
                    MATCH (n)
                    WHERE n.dataset_id = $dataset_id AND n.name IS NOT NULL
                    SET n.canonical_name = toLower(trim(n.name))
                    """,
                    dataset_id=dataset_id,
                )

                # APOC merge if available (best effort).
                # If APOC is missing, this block fails safely and graph remains usable.
                try:
                    await session.run(
                        """
                        MATCH (n)
                        WHERE n.dataset_id = $dataset_id AND n.canonical_name IS NOT NULL
                        WITH n.canonical_name AS key, collect(n) AS nodes
                        WHERE size(nodes) > 1
                        CALL apoc.refactor.mergeNodes(nodes, {properties: "combine", mergeRels: true}) YIELD node
                        RETURN count(node) AS merged_count
                        """,
                        dataset_id=dataset_id,
                    )
                except Exception:
                    pass

            await driver.close()
            
            
        except Exception as e:
            print(f"Error during graph normalization: {e}")