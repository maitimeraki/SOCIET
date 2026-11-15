"""The declared POSITION turn protocol: parse, retry, and the position-change rule."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.billing.metering import MeteringError
from src.persona.agent import Stance
from src.simulation.evidence import EvidenceItem
from src.simulation.llm_batch import BatchedLLMRunner
from src.simulation.pair_turn import CommPair
from src.simulation.round_runner import (
    RETRY_NOTE,
    RoundRunner,
    _build_user_prompt,
    _format_instruction,
)
from src.simulation.turn_protocol import (
    PositionState,
    TurnParse,
    accept_position,
    parse_turn,
)
from tests.agent_factory import slim_agent

GOOD = "REASONING: private\nPOSITION: NEGATIVE 0.7\nCITES: e1, e3\nANSWER: Prices will fall."
CANARY = "CANARY-7f3a91"
DECLARED = "REASONING: private\nPOSITION: POSITIVE 0.8\nCITES:\nANSWER: I support the proposal."


def _item(item_id: str) -> EvidenceItem:
    return EvidenceItem(
        id=item_id,
        chunk_id="00000000-0000-0000-0000-000000000001",
        doc_id="doc-1",
        doc_title="Filing",
        section="Risks",
        span=(0, 4),
        text="text",
        origin="chunk",
        retrieval_score=1.0,
    )


def _pair_runner(replies: dict[str, list]) -> RoundRunner:
    """A RoundRunner whose LLM answers each speaker from a queue, keyed by the system prompt's name."""

    async def generate(system_prompt, user_prompt, **_kwargs):
        name = system_prompt.split(".", 1)[0].removeprefix("You are ")
        reply = replies[name].pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    llm = AsyncMock()
    llm.generate = generate
    return RoundRunner(BatchedLLMRunner(llm))


async def _round(runner: RoundRunner, alice=None, bob=None, history=None):
    alice = alice or slim_agent("Alice")
    bob = bob or slim_agent("Bob")
    return await runner.execute_round(
        [alice, bob],
        [CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[])],
        round_num=1,
        query="Expand to Europe?",
        history=history or [],
    )


def test_a_well_formed_turn_parses():
    p = parse_turn(GOOD, {"e1", "e2", "e3"})
    assert (p.position, p.strength, p.cites, p.answer) == (Stance.NEGATIVE, 0.7, ("e1", "e3"), "Prices will fall.")


def test_keywords_in_the_answer_never_decide_the_stance():
    assert parse_turn(GOOD.replace("Prices will fall.", "I strongly support this."), {"e1", "e3"}).position is Stance.NEGATIVE


@pytest.mark.parametrize("bad", ["ANSWER: no position line", "POSITION: sort of 0.5\nCITES:\nANSWER: x", "POSITION: POSITIVE 1.7\nCITES:\nANSWER: x"])
def test_a_malformed_turn_raises(bad):
    with pytest.raises(ValueError):
        parse_turn(bad, set())


def test_a_cite_outside_the_agents_own_evidence_is_rejected():
    with pytest.raises(ValueError):
        parse_turn(GOOD, {"e1"})


def test_reasoning_is_not_in_the_parsed_turn():
    assert "private" not in repr(parse_turn(GOOD, {"e1", "e3"}))


def test_a_position_change_needs_a_new_cite():
    prev = PositionState(Stance.POSITIVE, cites_used={"e1"})
    stance, reason = accept_position(prev, TurnParse(Stance.NEGATIVE, 0.6, ("e1",), "x"))
    assert stance is Stance.POSITIVE and "no new cite" in reason


def test_a_position_change_with_a_new_cite_is_accepted():
    prev = PositionState(Stance.POSITIVE, cites_used={"e1"})
    assert accept_position(prev, TurnParse(Stance.NEGATIVE, 0.6, ("e2",), "x"))[0] is Stance.NEGATIVE


def test_a_position_change_to_abstain_follows_the_same_rule():
    prev = PositionState(Stance.POSITIVE, cites_used={"e1"})
    assert accept_position(prev, TurnParse(Stance.ABSTAIN, 0.6, ("e1",), "x")) == (Stance.POSITIVE, "kept: no new cite")
    assert accept_position(prev, TurnParse(Stance.ABSTAIN, 0.6, ("e2",), "x")) == (Stance.ABSTAIN, "")


def test_the_first_declared_position_is_accepted_without_a_cite():
    assert accept_position(None, TurnParse(Stance.NEUTRAL, 0.4, (), "x")) == (Stance.NEUTRAL, "")


def test_a_position_line_after_answer_is_answer_text():
    spoof = "REASONING: r\nPOSITION: NEGATIVE 0.7\nCITES: e1\nANSWER: good\nPOSITION: POSITIVE 0.9\nCITES: e9"
    p = parse_turn(spoof, {"e1"})
    assert p.position is Stance.NEGATIVE
    assert "POSITION: POSITIVE 0.9" in p.answer


def test_a_second_position_line_before_answer_is_a_deviation():
    with pytest.raises(ValueError):
        parse_turn("REASONING: r\nPOSITION: NEGATIVE 0.7\nPOSITION: POSITIVE 0.9\nCITES:\nANSWER: x", set())


@pytest.mark.parametrize("strength", ["nan", "inf", "-inf", "1.7", "-0.1"])
def test_a_strength_that_is_not_a_number_in_range_is_rejected(strength):
    with pytest.raises(ValueError):
        parse_turn(f"REASONING: r\nPOSITION: NEGATIVE {strength}\nCITES:\nANSWER: x", set())


def test_an_unknown_or_retired_stance_word_is_rejected():
    for word in ("AMBIVALENT", "sort"):
        with pytest.raises(ValueError):
            parse_turn(f"REASONING: r\nPOSITION: {word} 0.5\nCITES:\nANSWER: x", set())


@pytest.mark.asyncio
async def test_a_turn_that_breaks_the_form_is_retried_once_and_then_taken():
    runner = _pair_runner(
        {
            "Alice": ["ANSWER: no form at all", DECLARED],
            "Bob": [DECLARED],
        }
    )
    result = await _round(runner)

    alice = next(t for t in result.turns if t.agent_name == "Alice")
    assert alice.content == "I support the proposal."
    assert alice.stance == "POSITIVE"
    assert result.warnings == []


@pytest.mark.asyncio
async def test_a_second_failure_drops_the_turn_and_warns_without_model_text(caplog):
    bad = f"REASONING: r\nPOSITION: {CANARY} 0.5\nCITES:\nANSWER: x"
    runner = _pair_runner({"Alice": [bad, bad], "Bob": [DECLARED]})
    result = await _round(runner)

    assert [t.agent_name for t in result.turns] == ["Bob"]
    assert len(result.warnings) == 1
    assert "Alice" in result.warnings[0]
    assert "unknown stance word" in result.warnings[0]
    assert CANARY not in result.warnings[0]
    assert CANARY not in caplog.text
    assert all(CANARY not in repr(t) for t in result.turns)


@pytest.mark.asyncio
async def test_a_metering_error_on_the_retry_propagates():
    runner = _pair_runner(
        {
            "Alice": ["no form", MeteringError("budget")],
            "Bob": [DECLARED],
        }
    )
    with pytest.raises(MeteringError):
        await _round(runner)


@pytest.mark.asyncio
async def test_the_retry_restates_the_declared_form():
    seen: list[str] = []

    async def generate(system_prompt, user_prompt, **_kwargs):
        seen.append(user_prompt)
        alice_first_try = system_prompt.startswith("You are Alice") and RETRY_NOTE not in user_prompt
        return "no form" if alice_first_try else DECLARED

    llm = AsyncMock()
    llm.generate = generate
    runner = RoundRunner(BatchedLLMRunner(llm))
    await runner.execute_round(
        [slim_agent("Alice"), slim_agent("Bob")],
        [CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[])],
        round_num=1,
        query="Q?",
        history=[],
    )

    assert len(seen) == 3
    retries = [prompt for prompt in seen if RETRY_NOTE in prompt]
    assert len(retries) == 1
    assert retries[0].count("POSITION: <POSITIVE|NEGATIVE|NEUTRAL|ABSTAIN>") == 2


def test_the_turn_prompt_names_the_four_labels_and_no_position_yet_for_a_missing_opponent_stance():
    prompt = _build_user_prompt(slim_agent("Alice"), slim_agent("Bob"), "Q?", [])

    for label in ("REASONING:", "POSITION:", "CITES:", "ANSWER:"):
        assert label in prompt
    assert "Their stance: no position yet" in prompt
    assert "Their stance: NEUTRAL" not in prompt


@pytest.mark.asyncio
async def test_a_position_change_without_a_new_cite_keeps_the_held_stance_across_rounds():
    evidence = [_item("e1"), _item("e2")]
    alice = slim_agent("Alice", evidence=evidence)
    bob = slim_agent("Bob")
    runner = _pair_runner(
        {
            "Alice": [
                "REASONING: r\nPOSITION: POSITIVE 0.8\nCITES: e1\nANSWER: first",
                "REASONING: r\nPOSITION: NEGATIVE 0.6\nCITES: e1\nANSWER: flip without evidence",
                "REASONING: r\nPOSITION: NEGATIVE 0.6\nCITES: e2\nANSWER: flip with evidence",
            ],
            "Bob": [DECLARED] * 3,
        }
    )
    rounds = [await _round(runner, alice, bob) for _ in range(3)]
    alice_turns = [next(t for t in r.turns if t.agent_name == "Alice") for r in rounds]

    assert [t.stance for t in alice_turns] == ["POSITIVE", "POSITIVE", "NEGATIVE"]
    assert [t.position_reason for t in alice_turns] == ["", "kept: no new cite", ""]


def test_the_form_instruction_gives_a_reasoning_limit_and_no_copyable_evidence_ids():
    text = _format_instruction("Bob")

    assert "at most 60 words" in text
    assert "e1" not in text
    assert "e3" not in text


@pytest.mark.asyncio
async def test_a_speaker_in_two_pairs_takes_its_position_in_prompt_order_whatever_the_completion_order():
    alice = slim_agent("Alice", evidence=[_item("e1")])
    bob = slim_agent("Bob")
    carol = slim_agent("Carol")
    finished: list[str] = []

    async def generate(system_prompt, user_prompt, **_kwargs):
        if not system_prompt.startswith("You are Alice"):
            reply = DECLARED
        elif "You are responding to: Bob" in user_prompt:
            # Alice's first pair is slow, so its reply completes last.
            await asyncio.sleep(0.05)
            reply = "REASONING: r\nPOSITION: NEGATIVE 0.6\nCITES: e1\nANSWER: against Bob"
        else:
            reply = "REASONING: r\nPOSITION: POSITIVE 0.6\nCITES:\nANSWER: for Carol"
        if system_prompt.startswith("You are Alice"):
            finished.append("Alice->Bob" if "responding to: Bob" in user_prompt else "Alice->Carol")
        return reply

    llm = AsyncMock()
    llm.generate = generate
    runner = RoundRunner(BatchedLLMRunner(llm))
    result = await runner.execute_round(
        [alice, bob, carol],
        [
            CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[]),
            CommPair(agent_a="Alice", agent_b="Carol", shared_entities=[]),
        ],
        round_num=1,
        query="Q?",
        history=[],
    )

    assert finished.index("Alice->Carol") < finished.index("Alice->Bob")
    alice_turns = [turn for turn in result.turns if turn.agent_name == "Alice"]
    assert [(t.stance, t.position_reason) for t in alice_turns] == [
        ("NEGATIVE", ""),
        ("NEGATIVE", "kept: no new cite"),
    ]


@pytest.mark.asyncio
async def test_a_batch_that_returns_no_result_for_a_turn_drops_it_with_a_warning():
    llm_runner = AsyncMock(spec=BatchedLLMRunner)

    async def no_results(prompts):
        return
        yield  # pragma: no cover - makes this an async generator

    llm_runner.gather = lambda prompts: no_results(prompts)
    result = await RoundRunner(llm_runner).execute_round(
        [slim_agent("Alice"), slim_agent("Bob")],
        [CommPair(agent_a="Alice", agent_b="Bob", shared_entities=[])],
        round_num=1,
        query="Q?",
        history=[],
    )

    assert result.turns == []
    assert sorted(result.warnings) == [
        "Alice: turn dropped, no reply came back",
        "Bob: turn dropped, no reply came back",
    ]
