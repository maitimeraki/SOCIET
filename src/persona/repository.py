import re
from typing import List, Dict, Any, cast, LiteralString
from neo4j import AsyncGraphDatabase


_SAFE_RELATION_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")


class PersonaRepository:
    def __init__(self, neo4j_uri: str, neo4j_user: str, neo4j_password: str, neo4j_database: str):
        self._driver = AsyncGraphDatabase.driver(
            neo4j_uri,
            auth=(neo4j_user, neo4j_password),
        )
        self._db = neo4j_database

    async def close(self) -> None:
        await self._driver.close()

    @staticmethod
    def _label_clause(archetype_label: str | None) -> str:
        if not archetype_label:
            return ""
        return f":{archetype_label}"

    async def list_agent_names(self, archetype_label: str | None = None, limit: int = 1000) -> List[str]:
        label_clause = self._label_clause(archetype_label)
        query = f"""
            MATCH (n{label_clause})
            WHERE n.name IS NOT NULL
            RETURN n.name AS name
            ORDER BY n.name
            LIMIT $limit
            """
        async with self._driver.session(database=self._db) as session:
            res = await session.run(cast(LiteralString, query), limit=limit)
            rows = await res.data()
        return [r["name"] for r in rows if r.get("name")]

    async def fetch_identity(self, archetype_label: str | None, name: str) -> Dict[str, Any] | None:
        label_clause = self._label_clause(archetype_label)
        query = f"""
        MATCH (n{label_clause} {{name: $name}})
        RETURN
          n.name AS name,
          coalesce(head(labels(n)), "Entity") AS archetype,
          coalesce(n.tone, n.communication_style, "strategic and factual") AS communication_style,
          coalesce(n.values, []) AS core_values,
          coalesce(n.culture, "") AS culture,
          coalesce(n.mission, "") AS mission
        LIMIT 1
        """
        async with self._driver.session(database=self._db) as session:
            res = await session.run(cast(LiteralString, query), name=name)
            row = await res.single()
        return dict(row) if row else None

    async def fetch_recent_memories(self, archetype_label: str | None, name: str, memory_limit: int = 30) -> List[Dict[str, Any]]:
        label_clause = self._label_clause(archetype_label)
        query = f"""
            MATCH (n{label_clause} {{name: $name}})
            OPTIONAL MATCH (n)-[r]->(m)
            WHERE m.name IS NOT NULL
            RETURN
            type(r) AS relation_type,
            m.name AS target_name,
            coalesce(r.summary, "") AS summary,
            coalesce(r.timestamp, "") AS timestamp
            ORDER BY coalesce(r.timestamp, "") DESC
            LIMIT $memory_limit
            """
        async with self._driver.session(database=self._db) as session:
            res = await session.run(cast(LiteralString, query), name=name, memory_limit=memory_limit)
            rows = await res.data()
        return rows

    async def fetch_relationships_to_targets(
        self,
        archetype_label: str | None,
        name: str,
        targets: List[str],
    ) -> List[Dict[str, Any]]:
        if not targets:
            return []

        label_clause = self._label_clause(archetype_label)
        query = f"""
        MATCH (a{label_clause} {{name: $name}})
        MATCH (b)
        WHERE b.name IN $targets
        OPTIONAL MATCH (a)-[r]->(b)
        RETURN b.name AS target_name, type(r) AS relation_type
        """
        async with self._driver.session(database=self._db) as session:
            res = await session.run(cast(LiteralString, query), name=name, targets=targets)
            rows = await res.data()
        return rows

    @staticmethod
    def _sanitize_relation_type(relation_type: str) -> str:
        cleaned = (relation_type or "").strip().upper().replace(" ", "_")
        if _SAFE_RELATION_RE.match(cleaned):
            return cleaned
        return "REACTED_TO"

    async def write_reaction_edge(
        self,
        archetype_label: str | None,
        source_name: str,
        target_name: str,
        relation_type: str,
        summary: str,
        round_no: int,
        dataset_id: str,
    ) -> None:
        if source_name == target_name:
            return

        safe_relation = self._sanitize_relation_type(relation_type)

        label_clause = self._label_clause(archetype_label)
        query = f"""
        MATCH (a{label_clause} {{name: $source_name}})
        MATCH (b {{name: $target_name}})
        MERGE (a)-[r:{safe_relation}]->(b)
        SET
          r.summary = $summary,
          r.round_no = $round_no,
          r.dataset_id = $dataset_id,
          r.timestamp = datetime().epochMillis
        """
        async with self._driver.session(database=self._db) as session:
            await session.run(
                cast(LiteralString, query),
                source_name=source_name,
                target_name=target_name,
                summary=summary,
                round_no=round_no,
                dataset_id=dataset_id,
            )
