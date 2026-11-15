"""A deliberation step in the turn: private REASONING, a declared POSITION, then the ANSWER.

The stance comes from the POSITION line only. The REASONING is dropped after parsing, so the
verdict never reads an agent's private thinking. The protocol itself is tested in
test_turn_protocol.py; these tests cover the prompt and the round-level result.
"""

from unittest.mock import AsyncMock

import pytest

from src.persona.agent import Agent
from src.simulation.llm_batch import BatchedLLMRunner
from src.simulation.pair_turn import CommPair
from src.simulation.round_runner import RoundRunner, _build_user_prompt
from tests.agent_factory import slim_agent

DELIBERATION = (
    "REASONING: Bob argues margins collapse. I am tempted to oppose the move for that "
    "reason, but scale absorbs it. We clash on whether volume offsets price.\n"
    "POSITION: POSITIVE 0.7\n"
    "CITES:\n"
    "ANSWER: I support the proposal: scale economics outweigh the short-term margin dip."
)


def _agent(name: str) -> Agent:
    return slim_agent(name, bio=f"{name} bio", details_raw=f"{name} perspective", confidence=0.6)


def test_user_prompt_instructs_the_declared_form():
    prompt = _build_user_prompt(_agent("Alice"), _agent("Bob"), "Expand to Europe?", [])
    assert "REASONING:" in prompt
    assert "POSITION:" in prompt
    assert "CITES:" in prompt
    assert "ANSWER:" in prompt


@pytest.mark.asyncio
async def test_execute_round_takes_the_answer_and_the_declared_position():
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(return_value=DELIBERATION)
    rr = RoundRunner(BatchedLLMRunner(mock_llm))
    alice, bob = _agent("Alice"), _agent("Bob")

    result = await rr.execute_round(
        [alice, bob],
        [CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[])],
        round_num=1,
        query="Expand to Europe?",
        history=[],
    )

    alice_turn = next(t for t in result.turns if t.agent_name == "Alice")
    assert (
        alice_turn.content
        == "I support the proposal: scale economics outweigh the short-term margin dip."
    )
    assert "REASONING" not in alice_turn.content
    assert alice_turn.stance == "POSITIVE"
    assert alice_turn.strength == 0.7


@pytest.mark.asyncio
async def test_execute_round_drops_a_reply_without_the_form_after_a_retry():
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(return_value="I oppose expansion outright.")
    rr = RoundRunner(BatchedLLMRunner(mock_llm))
    alice, bob = _agent("Alice"), _agent("Bob")

    result = await rr.execute_round(
        [alice, bob],
        [CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[])],
        round_num=1,
        query="Expand to Europe?",
        history=[],
    )

    assert result.turns == []
    assert len(result.warnings) == 2
    assert all("text outside a labelled section" in w for w in result.warnings)
