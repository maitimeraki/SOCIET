import re
from typing import List, Dict, Any, cast, LiteralString
from neo4j import AsyncGraphDatabase
from src.logging.setup_logging import setup_logging

logger = setup_logging()

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

    async def search_agents_by_query(self, archetype_label: str | None, query_tokens: List[str], limit: int = 100) -> List[Dict[str, Any]]:
        """Search nodes of the given archetype by matching any string property against any of the provided tokens.

        Returns rows with at least the `name` property when available and the matched properties.
        """
        label_clause = self._label_clause(archetype_label)
        # Simpler Cypher: return nodes and perform token matching in Python to avoid type coercion errors
        query = f"""
        MATCH (n{label_clause})
        RETURN n LIMIT $limit
        """
        async with self._driver.session(database=self._db) as session:
            res = await session.run(cast(LiteralString, query), limit=limit)
            rows = await res.data()
        logger.info(f"Search returned {len(rows)} rows from the database for archetype '{archetype_label}' with tokens {query_tokens}")

        tokens = [t.lower() for t in query_tokens]
        out: List[Dict[str, Any]] = []
        for r in rows:
            node = r.get("n")
            if not node:
                continue
            props = dict(node._properties) if hasattr(node, '_properties') else (node if isinstance(node, dict) else dict(node))

            # check any string property or list-of-strings contains any token
            matched = False
            for v in props.values():
                if isinstance(v, str):
                    lv = v.lower()
                    if any(tok in lv for tok in tokens):
                        matched = True
                        break
                # lists: only consider list of strings
                if isinstance(v, list) and v:
                    if all(isinstance(x, str) for x in v):
                        joined = " ".join(v).lower()
                        if any(tok in joined for tok in tokens):
                            matched = True
                            break
                # skip other types (numbers, float arrays like embeddings)

            if matched:
                out.append(props)
        
        logger.info(f"After token filtering, {len(out)} rows matched the query tokens {query_tokens} for archetype '{archetype_label}'")
        # If no matches found using the general scan, try a targeted Cypher search
        if not out:
            try:
                # Only search well-known textual fields to avoid coercion of non-string properties
                targeted_query = f"""
                MATCH (n{label_clause})
                WHERE ANY(t IN $tokens WHERE
                  toLower(coalesce(n.name, '')) CONTAINS t OR
                  toLower(coalesce(n.title, '')) CONTAINS t OR
                  toLower(coalesce(n.summary, '')) CONTAINS t OR
                  toLower(coalesce(n.description, '')) CONTAINS t OR
                  toLower(coalesce(n.domain_tags, '')) CONTAINS t
                )
                RETURN n LIMIT $limit
                """
                async with self._driver.session(database=self._db) as session:
                    res = await session.run(cast(LiteralString, targeted_query), tokens=tokens, limit=limit)
                    trows = await res.data()

                for r in trows:
                    node = r.get("n")
                    if not node:
                        continue
                    props = dict(node._properties) if hasattr(node, '_properties') else (node if isinstance(node, dict) else dict(node))
                    out.append(props)
            except Exception:
                # Avoid raising; we'll return whatever we have (possibly empty)
                logger.exception("Targeted Cypher fallback failed")

        return out

    async def fetch_agent_node(self, archetype_label: str | None, name: str) -> Dict[str, Any] | None:
        """Return all properties for a node with the given name and optional archetype label."""
        label_clause = self._label_clause(archetype_label)
        query = f"""
        MATCH (n{label_clause} {{name: $name}})
        RETURN n LIMIT 1
        """
        async with self._driver.session(database=self._db) as session:
            res = await session.run(cast(LiteralString, query), name=name)
            row = await res.single()
        if not row:
            return None
        node = row.get("n")
        return dict(node._properties) if node else None

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
        """Retrieve recent relationships/memories from agent that Maintains conversation context and agent memory across rounds"""
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
        """Write an edge representing a reaction from source_name to target_name with the given relation_type and summary."""
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
