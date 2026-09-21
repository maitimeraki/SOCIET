"""
ResponseTracker: Track agent responses and update persona state in Neo4j.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from neo4j import AsyncGraphDatabase
from typing import cast, LiteralString

from src.simulation.agent_node import AgentNode, Stance
from src.graph.config_graph import GraphConfig
from src.logging.setup_logging import setup_logging

logger = setup_logging()


@dataclass
class AgentTurn:
    """Represents a single agent response turn."""
    agent_id: str
    query: str
    response: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    stance: Stance = Stance.NEUTRAL
    confidence: float = 0.5
    round: int = 0


class ResponseTracker:
    """Track agent responses and update dynamic persona state in Neo4j."""

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

    async def record_response(self, agent_id: str, query: str, response: AgentTurn) -> None:
        """Store agent's response to a query.

        Creates a :RESPONDED_TO relationship on the agent node for audit trail
        and stores the turn data as properties on the relationship.
        """
        stance_val = response.stance.value if hasattr(response.stance, "value") else str(response.stance)

        query_cypher = """
        MATCH (a:Agent {id: $agent_id})
        CREATE (a)-[r:RESPONDED_TO {
            query: $query,
            response: $response,
            timestamp: datetime($timestamp),
            stance: $stance,
            confidence: $confidence,
            round: $round
        }]->()
        RETURN id(r) AS rel_id
        """

        params = {
            "agent_id": agent_id,
            "query": query,
            "response": response.response,
            "timestamp": response.timestamp.isoformat(),
            "stance": stance_val,
            "confidence": response.confidence,
            "round": response.round,
        }

        async with self._driver.session(database=self._db) as session:
            await session.run(cast(LiteralString, query_cypher), **params)

    async def get_response_history(self, agent_id: str, limit: int = 10) -> List[AgentTurn]:
        """Retrieve agent's past responses.

        Args:
            agent_id: The agent's UUID string.
            limit: Maximum number of responses to return (default 10).

        Returns:
            List of AgentTurn objects ordered by most recent first.
        """
        query_cypher = """
        MATCH (a:Agent {id: $agent_id})-[r:RESPONDED_TO]->()
        RETURN r.query AS query,
               r.response AS response,
               r.timestamp AS timestamp,
               r.stance AS stance,
               r.confidence AS confidence,
               r.round AS round
        ORDER BY r.timestamp DESC
        LIMIT $limit
        """

        async with self._driver.session(database=self._db) as session:
            result = await session.run(
                cast(LiteralString, query_cypher),
                agent_id=agent_id,
                limit=limit,
            )
            records = await result.data()

        turns = []
        for record in records:
            try:
                stance = Stance(record.get("stance", "NEUTRAL"))
            except Exception:
                stance = Stance.NEUTRAL

            ts = record.get("timestamp")
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts)
                except Exception:
                    ts = datetime.utcnow()
            elif not isinstance(ts, datetime):
                ts = datetime.utcnow()

            turns.append(AgentTurn(
                agent_id=agent_id,
                query=record.get("query", ""),
                response=record.get("response", ""),
                timestamp=ts,
                stance=stance,
                confidence=float(record.get("confidence", 0.5)),
                round=int(record.get("round", 0)),
            ))

        return turns

    async def update_persona_state(self, agent_id: str, result: AgentTurn) -> None:
        """Update agent's dynamic fields based on response.

        Updates:
            - last_query = current query
            - last_response = current response
            - activation_count += 1
        """
        query_cypher = """
        MATCH (a:Agent {id: $agent_id})
        SET a.last_query = $query,
            a.last_response = $response,
            a.activation_count = coalesce(a.activation_count, 0) + 1,
            a.updated_at = datetime()
        RETURN a.id AS id
        """

        params = {
            "agent_id": agent_id,
            "query": result.query,
            "response": result.response,
        }

        async with self._driver.session(database=self._db) as session:
            await session.run(cast(LiteralString, query_cypher), **params)

    async def get_agent(self, agent_id: str) -> Optional[AgentNode]:
        """Get agent by ID."""
        from src.persona.agent_repository import AgentRepository
        repo = AgentRepository(self._config)
        try:
            return await repo.get_agent(agent_id)
        finally:
            await repo.close()

    async def get_activation_count(self, agent_id: str) -> int:
        """Get current activation count for an agent."""
        query_cypher = """
        MATCH (a:Agent {id: $agent_id})
        RETURN coalesce(a.activation_count, 0) AS count
        """

        async with self._driver.session(database=self._db) as session:
            result = await session.run(cast(LiteralString, query_cypher), agent_id=agent_id)
            record = await result.single()

        if record is None:
            return 0
        return int(record.get("count", 0))


if __name__ == "__main__":
    import asyncio

    async def test():
        tracker = ResponseTracker()

        # Create test agent first
        from src.persona.agent_repository import AgentRepository
        from src.simulation.agent_node import AgentNode, Stance

        repo = AgentRepository()
        agent = AgentNode(
            name="Test Response Agent",
            archetype="TEST",
            stance=Stance.NEUTRAL,
        )
        created = await repo.create_agent(agent)
        agent_id = str(created.id)
        print(f"Created agent: {agent_id}")
        await repo.close()

        # Test record_response
        turn = AgentTurn(
            agent_id=agent_id,
            query="What is the market outlook?",
            response="The market shows positive trends.",
            stance=Stance.POSITIVE,
            confidence=0.8,
            round=1,
        )
        await tracker.record_response(agent_id, turn.query, turn)
        print("Recorded response")

        # Test get_response_history
        history = await tracker.get_response_history(agent_id, limit=5)
        print(f"History count: {len(history)}")

        # Test update_persona_state
        await tracker.update_persona_state(agent_id, turn)
        print("Updated persona state")

        # Test get_activation_count
        count = await tracker.get_activation_count(agent_id)
        print(f"Activation count: {count}")

        # Cleanup
        await repo.close()
        agent_repo = AgentRepository()
        await agent_repo.delete_agent(agent_id)
        await agent_repo.close()
        await tracker.close()
        print("Done")

    asyncio.run(test())
