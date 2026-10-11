"""The speaker sees the opponent's actual argument, not just its stance label.

When the in-round history already carries the opponent's prior turn, the user
prompt surfaces that turn's verbatim text (bounded) under a labelled block, so
an agent rebuts the real claim instead of a strawman. Round 1 has no opponent
turn, so the block is omitted entirely and the stance line is unchanged.
"""
from src.persona.agent import Agent, DiscoveryType, PersonaIdentity
from src.simulation.round_runner import OPPONENT_STATEMENT_CHARS, _build_user_prompt


def _agent(name: str = "A") -> Agent:
    return Agent(
        identity=PersonaIdentity(name=name, archetype="x", communication_style="y"),
        discovery_type=DiscoveryType.GRAPH_DISCOVERY,
    )


def _turn(name: str, content: str, stance: str = "NEGATIVE") -> dict:
    return {"agent_name": name, "content": content, "stance": stance}


def test_prompt_shows_opponent_statement_text_in_labelled_block():
    prompt = _build_user_prompt(
        _agent("Alice"),
        _agent("Bob"),
        "q",
        [_turn("Bob", "We must not expand into Europe because margins collapse.")],
    )

    assert "WHAT Bob JUST ARGUED" in prompt
    assert "We must not expand into Europe because margins collapse." in prompt


def test_prompt_keeps_opponent_stance_line():
    prompt = _build_user_prompt(
        _agent("Alice"), _agent("Bob"), "q", [_turn("Bob", "hello", stance="NEGATIVE")]
    )

    assert "Their stance: NEGATIVE" in prompt


def test_prompt_omits_block_when_opponent_has_no_prior_turn():
    """Round 1: no opponent turn in history → no header, prompt stays valid."""
    prompt = _build_user_prompt(_agent("Alice"), _agent("Bob"), "q", [])

    assert "JUST ARGUED" not in prompt
    assert "Their stance:" in prompt


def test_prompt_truncates_long_statement_at_word_boundary():
    prompt = _build_user_prompt(
        _agent("Alice"), _agent("Bob"), "q", [_turn("Bob", "word " * 500)]
    )

    block = prompt.split("WHAT Bob JUST ARGUED:\n", 1)[1]
    said = block.split("\n", 1)[0]
    assert len(said) <= OPPONENT_STATEMENT_CHARS
    assert not said.endswith(" ")  # cut on a boundary, not mid-space
