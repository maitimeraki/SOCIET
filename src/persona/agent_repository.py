"""
AgentRepository: CRUD operations for AgentNode entities in Neo4j.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID

from neo4j import AsyncGraphDatabase, Record
from typing import cast, LiteralString

from src.simulation.agent_node import AgentNode, Stance
from src.graph.config_graph import GraphConfig
from src.logging.setup_logging import setup_logging

logger = setup_logging()


class AgentRepository:
    """CRUD repository for AgentNode entities stored in Neo4j."""

    def __init__(self, config: GraphConfig | None = None):
        self._config = config or GraphConfig()
        self._driver = AsyncGraphDatabase.driver(
            self._config.neo4j_uri,
            auth=(self._config.neo4j_username, self._config.neo4j_password),
        )
        self._db = self._config.neo4j_database

    async def close(self) -> None:
        """Close the Neo4j driver."""
        await self._driver.close()

    @staticmethod
    def _node_props(node: Any) -> Dict[str, Any]:
        """Extract properties from a Neo4j node."""
        if node is None:
            return {}
        try:
            if isinstance(node, dict):
                return dict(node)
            if hasattr(node, "_properties"):
                return dict(node._properties)
            if hasattr(node, "properties"):
                return dict(node.properties)
            return dict(node)
        except Exception:
            logger.exception("Failed to extract node properties")
            return {}

    @staticmethod
    def _record_to_agent(record: Record, alias: str = "n") -> AgentNode:
        """Convert a Neo4j record to an AgentNode."""
        node = record.get(alias) if alias else record.values()[0]
        props = AgentRepository._node_props(node)
        return AgentRepository._dict_to_agent(props)

    @staticmethod
    def _dict_to_agent(props: Dict[str, Any]) -> AgentNode:
        """Convert a property dict to an AgentNode."""
        # Handle UUID string conversion
        agent_id = props.get("id")
        if isinstance(agent_id, str):
            try:
                agent_id = UUID(agent_id)
            except Exception:
                agent_id = None

        # Parse stance
        stance_val = props.get("stance", Stance.NEUTRAL.value)
        try:
            stance = Stance(stance_val)
        except Exception:
            stance = Stance.NEUTRAL

        # Parse datetime
        created_at = props.get("created_at")
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at)
            except Exception:
                created_at = datetime.utcnow()
        elif not isinstance(created_at, datetime):
            created_at = datetime.utcnow()

        updated_at = props.get("updated_at")
        if isinstance(updated_at, str):
            try:
                updated_at = datetime.fromisoformat(updated_at)
            except Exception:
                updated_at = datetime.utcnow()
        elif not isinstance(updated_at, datetime):
            updated_at = datetime.utcnow()

        # Parse list fields
        instinct_tags = props.get("instinct_tags", [])
        if isinstance(instinct_tags, str):
            instinct_tags = [t.strip() for t in instinct_tags.split(",") if t.strip()]

        domain_tags = props.get("domain_tags", [])
        if isinstance(domain_tags, str):
            domain_tags = [t.strip() for t in domain_tags.split(",") if t.strip()]

        entity_affinity = props.get("entity_affinity", [])
        if isinstance(entity_affinity, str):
            entity_affinity = [t.strip() for t in entity_affinity.split(",") if t.strip()]

        expertise_areas = props.get("expertise_areas", [])
        if isinstance(expertise_areas, str):
            expertise_areas = [t.strip() for t in expertise_areas.split(",") if t.strip()]

        return AgentNode(
            id=agent_id,
            name=props.get("name", ""),
            archetype=props.get("archetype", ""),
            created_at=created_at,
            updated_at=updated_at,
            stance=stance,
            intensity=float(props.get("intensity", 0.5)),
            confidence=float(props.get("confidence", 0.5)),
            belief=props.get("belief", ""),
            conviction=float(props.get("conviction", 0.5)),
            opinion=props.get("opinion", ""),
            cior=float(props.get("cior", 0.0)),
            instinct_tags=instinct_tags,
            domain_tags=domain_tags,
            entity_affinity=entity_affinity,
            communication_radius=int(props.get("communication_radius", 1)),
            role_description=props.get("role_description", ""),
            expertise_areas=expertise_areas,
            display_order=int(props.get("display_order", 0)),
            last_query=props.get("last_query", ""),
            last_response=props.get("last_response", ""),
            activation_count=int(props.get("activation_count", 0)),
        )

    async def create_agent(self, entity_node: AgentNode) -> AgentNode:
        """Create a new Agent node in Neo4j.

        Args:
            entity_node: AgentNode to persist. ID will be assigned if not provided.

        Returns:
            The created AgentNode with populated ID and timestamps.
        """
        agent = entity_node
        if not agent.id:
            agent = AgentNode(
                name=agent.name,
                archetype=agent.archetype,
                stance=agent.stance,
                intensity=agent.intensity,
                confidence=agent.confidence,
                belief=agent.belief,
                conviction=agent.conviction,
                opinion=agent.opinion,
                cior=agent.cior,
                instinct_tags=agent.instinct_tags,
                domain_tags=agent.domain_tags,
                entity_affinity=agent.entity_affinity,
                communication_radius=agent.communication_radius,
                role_description=agent.role_description,
                expertise_areas=agent.expertise_areas,
                display_order=agent.display_order,
            )

        query = """
        CREATE (n:Agent)
        SET n = $props
        RETURN n
        """
        props = {
            "id": str(agent.id),
            "name": agent.name,
            "archetype": agent.archetype,
            "created_at": agent.created_at.isoformat(),
            "updated_at": agent.updated_at.isoformat(),
            "stance": agent.stance.value if hasattr(agent.stance, "value") else agent.stance,
            "intensity": agent.intensity,
            "confidence": agent.confidence,
            "belief": agent.belief,
            "conviction": agent.conviction,
            "opinion": agent.opinion,
            "cior": agent.cior,
            "instinct_tags": agent.instinct_tags,
            "domain_tags": agent.domain_tags,
            "entity_affinity": agent.entity_affinity,
            "communication_radius": agent.communication_radius,
            "role_description": agent.role_description,
            "expertise_areas": agent.expertise_areas,
            "display_order": agent.display_order,
            "last_query": agent.last_query,
            "last_response": agent.last_response,
            "activation_count": agent.activation_count,
        }

        async with self._driver.session(database=self._db) as session:
            result = await session.run(cast(LiteralString, query), props=props)
            record = await result.single()

        if record is None:
            raise RuntimeError("Failed to create agent node")

        return self._record_to_agent(record)

    async def get_agent(self, agent_id: str) -> Optional[AgentNode]:
        """Get a single agent by ID.

        Args:
            agent_id: UUID string of the agent.

        Returns:
            AgentNode if found, None otherwise.
        """
        query = """
        MATCH (n:Agent {id: $agent_id})
        RETURN n
        """
        async with self._driver.session(database=self._db) as session:
            result = await session.run(cast(LiteralString, query), agent_id=agent_id)
            record = await result.single()

        if record is None:
            return None

        return self._record_to_agent(record)

    async def update_agent(self, agent_id: str, updates: Dict[str, Any]) -> Optional[AgentNode]:
        """Update an existing agent.

        Args:
            agent_id: UUID string of the agent to update.
            updates: Dict of fields to update.

        Returns:
            Updated AgentNode if found, None if not found.
        """
        # Build SET clause dynamically
        set_parts = []
        params: Dict[str, Any] = {"agent_id": agent_id}

        # Whitelist allowed update fields
        allowed_fields = {
            "name", "archetype", "stance", "intensity", "confidence",
            "belief", "conviction", "opinion", "cior", "instinct_tags",
            "domain_tags", "entity_affinity", "communication_radius",
            "role_description", "expertise_areas", "display_order",
            "last_query", "last_response", "activation_count",
        }

        for key, value in updates.items():
            if key not in allowed_fields:
                continue

            if key == "stance" and isinstance(value, str):
                try:
                    value = Stance(value).value
                except Exception:
                    continue
            elif key in ("instinct_tags", "domain_tags", "entity_affinity", "expertise_areas"):
                if isinstance(value, str):
                    value = [t.strip() for t in value.split(",") if t.strip()]

            set_parts.append(f"n.{key} = ${key}")
            params[key] = value

        if not set_parts:
            # No valid updates, just return current state
            return await self.get_agent(agent_id)

        # Always update timestamp
        set_parts.append("n.updated_at = $updated_at")
        params["updated_at"] = datetime.utcnow().isoformat()

        query = f"""
        MATCH (n:Agent {{id: $agent_id}})
        SET {', '.join(set_parts)}
        RETURN n
        """

        async with self._driver.session(database=self._db) as session:
            result = await session.run(cast(LiteralString, query), **params)
            record = await result.single()

        if record is None:
            return None

        return self._record_to_agent(record)

    async def list_agents(self, filters: Dict[str, Any] | None = None) -> List[AgentNode]:
        """List agents with optional filtering.

        Args:
            filters: Optional dict with filter criteria.
                - archetype: Filter by agent archetype
                - domain_tags: Filter by domain tags (list or comma-separated string)
                - stance: Filter by stance value
                - min_confidence: Minimum confidence threshold
                - limit: Max results to return
                - offset: Skip first N results

        Returns:
            List of matching AgentNode objects.
        """
        filters = filters or {}
        query_parts = ["MATCH (n:Agent)"]
        where_parts = []
        params: Dict[str, Any] = {}

        # archetype filter
        if "archetype" in filters:
            where_parts.append("n.archetype = $archetype")
            params["archetype"] = filters["archetype"]

        # stance filter
        if "stance" in filters:
            stance_val = filters["stance"]
            if hasattr(stance_val, "value"):
                stance_val = stance_val.value
            where_parts.append("n.stance = $stance")
            params["stance"] = stance_val

        # domain_tags filter
        if "domain_tags" in filters:
            tags = filters["domain_tags"]
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            if tags:
                where_parts.append("ANY(tag IN $domain_tags WHERE tag IN n.domain_tags)")
                params["domain_tags"] = tags

        # min_confidence filter
        if "min_confidence" in filters:
            where_parts.append("n.confidence >= $min_confidence")
            params["min_confidence"] = float(filters["min_confidence"])

        # Build final query
        query = "\n".join(query_parts)
        if where_parts:
            query += "\nWHERE " + "\nAND ".join(where_parts)
        query += "\nRETURN n"

        # Ordering
        order_by = filters.get("order_by", "n.created_at")
        order_dir = filters.get("order_dir", "DESC")
        if order_dir not in ("ASC", "DESC"):
            order_dir = "DESC"
        query += f"\nORDER BY {order_by} {order_dir}"

        # Pagination
        limit = filters.get("limit", 100)
        offset = filters.get("offset", 0)
        query += f"\nSKIP {offset}\nLIMIT {limit}"

        async with self._driver.session(database=self._db) as session:
            result = await session.run(cast(LiteralString, query), **params)
            records = await result.data()

        return [self._record_to_agent(record) for record in records]

    async def delete_agent(self, agent_id: str) -> bool:
        """Delete an agent by ID.

        Args:
            agent_id: UUID string of the agent to delete.

        Returns:
            True if deleted, False if not found.
        """
        query = """
        MATCH (n:Agent {id: $agent_id})
        DELETE n
        RETURN count(n) AS deleted
        """
        async with self._driver.session(database=self._db) as session:
            result = await session.run(cast(LiteralString, query), agent_id=agent_id)
            record = await result.single()

        if record is None:
            return False

        return record.get("deleted", 0) > 0


if __name__ == "__main__":
    import asyncio

    async def test():
        config = GraphConfig()
        repo = AgentRepository(config)

        # Test create
        agent = AgentNode(
            name="Test Analyst",
            archetype="MARKET_ANALYST",
            domain_tags=["finance", "markets"],
            stance=Stance.NEUTRAL,
        )
        created = await repo.create_agent(agent)
        print(f"Created: {created.id} - {created.name}")

        # Test get
        fetched = await repo.get_agent(str(created.id))
        print(f"Fetched: {fetched.name if fetched else 'NOT FOUND'}")

        # Test list
        agents = await repo.list_agents({"archetype": "MARKET_ANALYST"})
        print(f"List by archetype: {len(agents)} agents")

        # Test update
        updated = await repo.update_agent(str(created.id), {"intensity": 0.8})
        print(f"Updated intensity: {updated.intensity if updated else 'FAILED'}")

        # Test delete
        deleted = await repo.delete_agent(str(created.id))
        print(f"Deleted: {deleted}")

        await repo.close()

    asyncio.run(test())
