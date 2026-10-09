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
from src.simulation.round_runner import _build_system_prompt


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
        _agent(bio="my bio", detailed_perspective="my perspective"),
        _agent(),
        ["SharedEntity"],
    )

    assert "my bio" in prompt
    assert "my perspective" in prompt
    assert "SharedEntity" in prompt


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
