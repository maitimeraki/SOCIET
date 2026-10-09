"""A deliberation step in the turn: reason first, then answer.

The user prompt asks the model to emit a short REASONING: section then an
ANSWER: section. Stance is parsed from the ANSWER only, never the reasoning --
otherwise the verdict would read an agent's private thinking instead of its
stated position. A response without the delimiter degrades to whole-text-as-answer.
"""
import pytest
from unittest.mock import AsyncMock

from src.persona.agent import Agent, ConfidenceBreakdown, DiscoveryType, ExpertiseLevel, PersonaIdentity
from src.simulation.llm_batch import BatchedLLMRunner
from src.simulation.pair_turn import CommPair
from src.simulation.round_runner import (
    RoundRunner,
    _build_user_prompt,
    _parse_response_stance,
    _split_reasoning_answer,
)

DELIBERATION = (
    "REASONING: Bob argues margins collapse. I am tempted to oppose the move for that "
    "reason, but scale absorbs it. We clash on whether volume offsets price.\n"
    "ANSWER: I support the proposal: scale economics outweigh the short-term margin dip."
)


def _agent(name: str) -> Agent:
    return Agent(
        identity=PersonaIdentity(name=name, archetype="Expert", communication_style="Formal"),
        discovery_type=DiscoveryType.INTENT_DRIVEN,
        expertise_level=ExpertiseLevel.TECHNICAL,
        bio=f"{name} bio",
        detailed_perspective=f"{name} perspective",
        domain_tags=["x"],
        confidence=0.6,
        confidence_breakdown=ConfidenceBreakdown(source_breadth=1, node_density=1, relationship_connectivity=0.5),
    )


# ------------------------------------------------------------------
# Prompt instruction (Step 3)
# ------------------------------------------------------------------

def test_user_prompt_instructs_reason_then_answer():
    prompt = _build_user_prompt(_agent("Alice"), _agent("Bob"), "Expand to Europe?", [])
    assert "REASONING:" in prompt
    assert "ANSWER:" in prompt


# ------------------------------------------------------------------
# Splitter (Step 3)
# ------------------------------------------------------------------

def test_splitter_separates_reasoning_from_answer():
    reasoning, answer = _split_reasoning_answer(DELIBERATION)
    assert reasoning.startswith("Bob argues margins collapse")
    assert "REASONING:" not in reasoning
    assert answer == "I support the proposal: scale economics outweigh the short-term margin dip."
    assert "ANSWER:" not in answer


def test_splitter_without_delimiter_treats_whole_text_as_answer():
    raw = "I support this but I am uncertain."
    reasoning, answer = _split_reasoning_answer(raw)
    assert reasoning == ""
    assert answer == raw


def test_splitter_with_empty_answer_degrades_to_whole_text():
    raw = "REASONING: thinking only, no answer marker content."
    reasoning, answer = _split_reasoning_answer(raw)
    assert reasoning == ""
    assert answer == raw


# ------------------------------------------------------------------
# Stance from answer, not reasoning (Steps 2, 5)
# ------------------------------------------------------------------

def test_parse_response_stance_still_reads_markers():
    # Regression: markers parsed identically when handed the answer section.
    assert _parse_response_stance("I support the proposal.", "NEUTRAL", 0.5)[0] == "POSITIVE"
    assert _parse_response_stance("I oppose the proposal.", "NEUTRAL", 0.5)[0] == "NEGATIVE"


def test_parse_response_stance_ignores_reasoning_markers():
    # Reasoning says "oppose", answer says "support": stance must come from the answer.
    _, answer = _split_reasoning_answer(DELIBERATION)
    assert _parse_response_stance(answer, "NEUTRAL", 0.5)[0] == "POSITIVE"
    # Without the split the whole text would read NEGATIVE (negative markers win).
    assert _parse_response_stance(DELIBERATION, "NEUTRAL", 0.5)[0] == "NEGATIVE"


# ------------------------------------------------------------------
# End-to-end through execute_round (Definition of done)
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_round_content_is_answer_and_stance_from_answer():
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
    assert alice_turn.content == "I support the proposal: scale economics outweigh the short-term margin dip."
    assert "REASONING:" not in alice_turn.content
    assert alice_turn.stance == "POSITIVE"


@pytest.mark.asyncio
async def test_execute_round_no_delimiter_keeps_whole_response():
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

    alice_turn = next(t for t in result.turns if t.agent_name == "Alice")
    assert alice_turn.content == "I oppose expansion outright."
    assert alice_turn.stance == "NEGATIVE"
