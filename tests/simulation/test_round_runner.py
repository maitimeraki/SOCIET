"""Tests for RoundRunner."""
import uuid
import pytest
from unittest.mock import AsyncMock

from src.persona.agent import Agent, ConfidenceBreakdown, DiscoveryType, ExpertiseLevel, PersonaIdentity
from src.simulation.llm_batch import BatchedLLMRunner
from src.simulation.round_runner import RoundRunner, _build_system_prompt, _build_user_prompt, _parse_response_stance
from src.simulation.pair_turn import RoundResult, CommPair


def make_profile(name: str, domain_tags: list[str], perspective: str, confidence: float) -> tuple[uuid.UUID, Agent]:
    aid = uuid.uuid4()
    agent = Agent(
        agent_id=aid,
        identity=PersonaIdentity(name=name, archetype="Expert", communication_style="Formal"),
        discovery_type=DiscoveryType.INTENT_DRIVEN,
        expertise_level=ExpertiseLevel.TECHNICAL,
        bio=f"{name} description",
        detailed_perspective=perspective,
        domain_tags=domain_tags,
        confidence=confidence,
        confidence_breakdown=ConfidenceBreakdown(source_breadth=1, node_density=1, relationship_connectivity=0.5),
    )
    return aid, agent


def make_pair(name_a: str, name_b: str, shared: list[str]) -> CommPair:
    return CommPair(agent_a=name_a, agent_b=name_b, shared_entities=shared, evidence=[])


# ------------------------------------------------------------------
# _parse_response_stance
# ------------------------------------------------------------------

def test_parse_stance_positive():
    stance, _ = _parse_response_stance("I fully support this approach", "NEUTRAL", 0.5)
    assert stance == "POSITIVE"


def test_parse_stance_negative():
    stance, _ = _parse_response_stance("I oppose this decision strongly", "NEUTRAL", 0.5)
    assert stance == "NEGATIVE"


def test_parse_stance_neutral():
    stance, _ = _parse_response_stance("This is a balanced view with both pros and cons", "POSITIVE", 0.5)
    assert stance == "NEUTRAL"


def test_parse_confidence_boost():
    _, conf = _parse_response_stance("This is definitely the right choice", "POSITIVE", 0.5)
    assert conf == 0.6


def test_parse_confidence_deduct():
    _, conf = _parse_response_stance("This might perhaps be the right choice", "POSITIVE", 0.5)
    assert conf == 0.4


def test_parse_confidence_capped():
    _, conf = _parse_response_stance("This is absolutely, clearly, definitely the right choice", "POSITIVE", 0.95)
    assert conf == 1.0


# ------------------------------------------------------------------
# Prompt builders
# ------------------------------------------------------------------

def test_system_prompt_uses_profile_fields():
    _, alice = make_profile("Alice", ["economics", "finance"], "Markets self-correct efficiently.", 0.8)
    _, bob = make_profile("Bob", ["environmental science"], "Externalities are not priced in.", 0.7)
    prompt = _build_system_prompt(alice, bob, ["carbon tax", "EPA"])
    assert "Alice" in prompt
    assert "economics" in prompt
    assert "Markets self-correct efficiently" in prompt


def test_system_prompt_truncates_perspective():
    _, alice = make_profile("Alice", ["x"], "x" * 1000, 0.8)
    _, bob = make_profile("Bob", ["y"], "y", 0.7)
    prompt = _build_system_prompt(alice, bob, [])
    assert len(prompt) < 1000 + 200


def test_user_prompt_includes_query():
    _, alice = make_profile("Alice", ["x"], "x", 0.8)
    _, bob = make_profile("Bob", ["y"], "y", 0.7)
    prompt = _build_user_prompt(alice, bob, "Should we tax carbon?", [])
    assert "carbon" in prompt.lower()


def test_user_prompt_includes_history():
    _, alice = make_profile("Alice", ["x"], "x", 0.8)
    _, bob = make_profile("Bob", ["y"], "y", 0.7)
    history = [{"agent_name": "Alice", "content": "Markets are efficient."}]
    prompt = _build_user_prompt(alice, bob, "Tax carbon?", history)
    assert "Alice" in prompt
    assert "Markets are efficient" in prompt


def test_user_prompt_shows_opponent_name():
    _, alice = make_profile("Alice", ["x"], "x", 0.8)
    _, bob = make_profile("Bob", ["y"], "y", 0.7)
    prompt = _build_user_prompt(alice, bob, "Tax carbon?", [])
    assert "Bob" in prompt


# ------------------------------------------------------------------
# RoundRunner.execute_round
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_round_returns_round_result():
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(return_value="I support the proposal.")
    runner = BatchedLLMRunner(mock_llm)
    rr = RoundRunner(runner)

    aid_alice, alice = make_profile("Alice", ["economics"], "Markets work.", 0.8)
    aid_bob, bob = make_profile("Bob", ["climate"], "Climate matters.", 0.7)
    profiles = [alice, bob]
    pairs = [make_pair("Alice", "Bob", ["carbon"])]

    result = await rr.execute_round(profiles, pairs, round_num=1, query="Tax carbon?", history=[])

    assert isinstance(result, RoundResult)
    assert result.round_num == 1
    assert len(result.turns) == 2


@pytest.mark.asyncio
async def test_execute_round_uses_profile_fields_in_prompts():
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(return_value="Response")
    runner = BatchedLLMRunner(mock_llm)
    rr = RoundRunner(runner)

    aid_alice, alice = make_profile("Alice", ["AI safety"], "AI alignment is critical.", 0.9)
    aid_bob, bob = make_profile("Bob", ["economics"], "Economic growth first.", 0.6)
    profiles = [alice, bob]
    pairs = [make_pair("Alice", "Bob", ["regulation"])]

    await rr.execute_round(profiles, pairs, round_num=1, query="Regulate AI?", history=[])

    calls = mock_llm.generate.call_args_list
    assert len(calls) == 2
    for c in calls:
        system = c.kwargs.get("system_prompt", c[1].get("system_prompt", "")) if hasattr(c, "kwargs") else ""
        assert "Alice" in system or "Bob" in system


@pytest.mark.asyncio
async def test_execute_round_ws_broadcast_called():
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(return_value="Response")
    runner = BatchedLLMRunner(mock_llm)
    ws_calls = []

    async def track_ws(msg):
        ws_calls.append(msg)

    rr = RoundRunner(runner, ws_broadcast=track_ws)

    aid_alice, alice = make_profile("Alice", ["x"], "x", 0.8)
    aid_bob, bob = make_profile("Bob", ["y"], "y", 0.7)
    profiles = [alice, bob]
    pairs = [make_pair("Alice", "Bob", [])]

    await rr.execute_round(profiles, pairs, round_num=1, query="Topic?", history=[])

    assert len(ws_calls) == 2
    for msg in ws_calls:
        assert msg["type"] == "pair_turn"
        assert "pair_id" in msg


@pytest.mark.asyncio
async def test_execute_round_error_continues():
    call_count = {"total": 0}

    async def tracking_generate(**kwargs):
        call_count["total"] += 1
        if call_count["total"] == 2:
            raise ValueError("intentional failure")
        return "ok response"

    mock_llm = AsyncMock()
    mock_llm.generate = tracking_generate
    runner = BatchedLLMRunner(mock_llm)
    rr = RoundRunner(runner)

    aid_alice, alice = make_profile("Alice", ["x"], "x", 0.8)
    aid_bob, bob = make_profile("Bob", ["y"], "y", 0.7)
    profiles = [alice, bob]
    pairs = [make_pair("Alice", "Bob", [])]

    result = await rr.execute_round(profiles, pairs, round_num=1, query="Topic?", history=[])

    assert isinstance(result, RoundResult)
    assert len(result.turns) >= 1


@pytest.mark.asyncio
async def test_execute_round_turn_contains_profile_data():
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(return_value="I am certain this is the right approach.")
    runner = BatchedLLMRunner(mock_llm)
    rr = RoundRunner(runner)

    aid_alice, alice = make_profile("Alice", ["x"], "x", 0.8)
    aid_bob, bob = make_profile("Bob", ["y"], "y", 0.6)
    profiles = [alice, bob]
    pairs = [make_pair("Alice", "Bob", [])]

    result = await rr.execute_round(profiles, pairs, round_num=1, query="Topic?", history=[])

    names = {t.agent_name for t in result.turns}
    assert names == {"Alice", "Bob"}
    confidences = {t.confidence for t in result.turns}
    # Both are boosted by "certain" word: Alice 0.8->0.9, Bob 0.6->0.7
    assert 0.9 in confidences
    assert 0.7 in confidences


# ------------------------------------------------------------------
# Turn references
# ------------------------------------------------------------------

from src.simulation.round_runner import _extract_references


def test_extract_references_matches_candidates_in_content():
    refs = _extract_references("Carbon tax hurts the EPA budget", ["EPA", "carbon tax", "unrelated"])
    assert refs == ["EPA", "carbon tax"]


def test_extract_references_caps_at_five():
    refs = _extract_references(" ".join(f"n{i}" for i in range(10)), [f"n{i}" for i in range(10)])
    assert len(refs) == 5


@pytest.mark.asyncio
async def test_execute_round_fills_references():
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(return_value="I disagree with Bob about carbon pricing.")
    rr = RoundRunner(BatchedLLMRunner(mock_llm))
    _, alice = make_profile("Alice", ["x"], "x", 0.8)
    _, bob = make_profile("Bob", ["y"], "y", 0.7)
    result = await rr.execute_round(
        [alice, bob], [make_pair("Alice", "Bob", ["carbon pricing"])], round_num=1, query="Q?", history=[]
    )
    alice_turn = next(t for t in result.turns if t.agent_name == "Alice")
    assert "Bob" in alice_turn.references
