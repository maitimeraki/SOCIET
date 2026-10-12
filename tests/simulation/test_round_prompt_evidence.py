"""The debate system prompt renders an agent's own source evidence.

A non-empty `Agent.source_evidence` adds one labelled block; an empty list adds
nothing at all (no stray header), so an agent with no fetched chunks looks
exactly as it did before this feature existed.
"""
from src.persona.agent import (
    SOURCE_EVIDENCE_MAX_SNIPPETS,
    SOURCE_EVIDENCE_SNIPPET_CHARS,
    Agent,
    DiscoveryType,
    PersonaIdentity,
)
from src.simulation.round_runner import PERSONA_PERSPECTIVE_CHARS, _build_system_prompt


def _agent(**over) -> Agent:
    base = dict(
        identity=PersonaIdentity(name="A", archetype="x", communication_style="y"),
        discovery_type=DiscoveryType.GRAPH_DISCOVERY,
    )
    base.update(over)
    return Agent(**base)


def test_prompt_includes_evidence_block():
    prompt = _build_system_prompt(
        _agent(source_evidence=["chunk one text"]), _agent(), []
    )

    assert "SOURCE EVIDENCE" in prompt
    assert "chunk one text" in prompt


def test_prompt_omits_block_when_empty():
    prompt = _build_system_prompt(_agent(), _agent(), [])

    assert "SOURCE EVIDENCE" not in prompt
    assert "\n\n\n" not in prompt


def test_prompt_keeps_existing_lines():
    prompt = _build_system_prompt(
        _agent(role_description="my role", detailed_perspective="my perspective"),
        _agent(),
        ["SharedEntity"],
    )

    assert "my role" in prompt
    assert "my perspective" in prompt
    assert "SharedEntity" in prompt


def test_full_perspective_reaches_prompt():
    """A ~1200-char perspective reaches the prompt whole (the old [:500] slice cut it)."""
    perspective = ("alpha beta gamma delta " * 50).strip()
    assert len(perspective) > 1000

    prompt = _build_system_prompt(
        _agent(detailed_perspective=perspective), _agent(), []
    )

    assert perspective in prompt


def test_prompt_truncates_long_snippet_at_word_boundary():
    prompt = _build_system_prompt(
        _agent(source_evidence=["word " * 500]), _agent(), []
    )

    rendered = [line[2:] for line in prompt.splitlines() if line.startswith("- ")]
    assert len(rendered) == 1
    assert len(rendered[0]) <= SOURCE_EVIDENCE_SNIPPET_CHARS
    assert not rendered[0].endswith(" ")  # cut on a boundary, not mid-space


def test_prompt_renders_at_most_max_snippets():
    evidence = [f"snippet number {i}" for i in range(SOURCE_EVIDENCE_MAX_SNIPPETS + 3)]
    prompt = _build_system_prompt(_agent(source_evidence=evidence), _agent(), [])

    rendered = [line for line in prompt.splitlines() if line.startswith("- ")]
    assert len(rendered) == SOURCE_EVIDENCE_MAX_SNIPPETS


def test_perspective_over_budget_is_bounded():
    """A runaway perspective is still capped — the prompt cannot blow up."""
    prompt = _build_system_prompt(
        _agent(detailed_perspective="word " * 2000), _agent(), []
    )

    line = next(l for l in prompt.splitlines() if l.startswith("Your perspective: "))
    assert len(line) - len("Your perspective: ") <= PERSONA_PERSPECTIVE_CHARS


def test_prompt_uses_role_description_not_bio():
    """The prompt's one-liner is the agent's role_description, not a bio slice."""
    prompt = _build_system_prompt(
        _agent(bio="a long narrative bio", role_description="Senior Grid Analyst"),
        _agent(),
        [],
    )

    assert "Senior Grid Analyst" in prompt
    assert "Bio:" not in prompt
