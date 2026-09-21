"""Write-back service: persist debate round turns to Neo4j as REACTED_TO edges."""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import AsyncGraphDatabase
    from src.simulation.pair_turn import RoundResult

logger = logging.getLogger(__name__)


class WriteBackService:
    def __init__(self, driver: "AsyncGraphDatabase", db: str):
        self._driver = driver
        self._db = db

    async def persist_round_turns(
        self,
        rounds: list["RoundResult"],
        dataset_id: str,
    ) -> None:
        for round_result in rounds:
            turn_data = []
            for pair in round_result.pairs:
                for turn in round_result.turns:
                    if turn.agent_id == pair.agent_a:
                        target_id = pair.agent_b
                    elif turn.agent_id == pair.agent_b:
                        target_id = pair.agent_a
                    else:
                        continue
                    if target_id == turn.agent_id:
                        continue
                    speaker_name = turn.agent_name
                    target_name = self._resolve_target_name(target_id, round_result.turns)
                    if not target_name:
                        continue
                    turn_data.append(
                        {
                            "speaker_name": speaker_name,
                            "target_name": target_name,
                            "round_no": round_result.round_num,
                            "summary": turn.content,
                            "stance": turn.stance,
                        }
                    )

            if not turn_data:
                continue

            query = """
            UNWIND $turns AS turn
            MATCH (a:Persona {name: turn.speaker_name, dataset_id: $dataset_id})
            MATCH (b:Persona {name: turn.target_name, dataset_id: $dataset_id})
            MERGE (a)-[r:REACTED_TO]->(b)
            SET r.round_no = turn.round_no,
                r.summary = turn.summary,
                r.stance = turn.stance,
                r.dataset_id = $dataset_id
            """
            try:
                async with self._driver.session(database=self._db) as session:
                    await session.run(query, turns=turn_data, dataset_id=dataset_id)
            except Exception:
                logger.exception("WriteBackService: failed to persist turns for round %s", round_result.round_num)

    @staticmethod
    def _resolve_target_name(target_id: str, turns: list) -> str | None:
        for turn in turns:
            if turn.agent_id == target_id:
                return turn.agent_name
        return None
