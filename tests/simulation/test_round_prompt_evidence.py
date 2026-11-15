"""The debate system prompt renders the agent's own voice and fenced evidence.

Evidence renders as `<evidence id=...>` blocks (at most PROMPT_EVIDENCE_MAX); an
agent with no evidence renders the word "none" and no fence at all. Attribute
values are stripped of markup so an id cannot close the fence (audit L-G4).
"""

from src.simulation.evidence import EvidenceItem
from src.simulation.round_runner import PROMPT_EVIDENCE_MAX, _build_system_prompt
from tests.agent_factory import slim_agent


def _item(i: int, text: str = "chunk text", item_id: str | None = None) -> EvidenceItem:
    return EvidenceItem(
        id=item_id or f"e{i}",
        chunk_id="00000000-0000-0000-0000-000000000001",
        doc_id="doc-1",
        doc_title="Filing",
        section="Risks",
        span=(0, len(text)),
        text=text,
        origin="chunk",
        retrieval_score=1.0,
    )


def test_prompt_includes_evidence_block():
    prompt = _build_system_prompt(slim_agent(evidence=[_item(1, "chunk one text")]), [])

    assert '<evidence id="e1"' in prompt
    assert "chunk one text" in prompt


def test_prompt_renders_none_and_no_fence_when_no_evidence():
    prompt = _build_system_prompt(slim_agent(), [])

    assert "<evidence" not in prompt
    assert "\n\n\n" not in prompt


def test_prompt_keeps_role_bio_stance_and_shared_entities():
    prompt = _build_system_prompt(slim_agent(role="my role", bio="my bio", details_raw="my perspective"), ["SharedEntity"])

    assert "my role" in prompt
    assert "my bio" in prompt
    assert "my perspective" in prompt
    assert "SharedEntity" in prompt


def test_full_profile_reaches_prompt_untruncated():
    details = ("alpha beta gamma delta " * 50).strip()
    assert len(details) > 1000

    prompt = _build_system_prompt(slim_agent(details_raw=details), [])

    assert details in prompt


def test_prompt_renders_at_most_max_evidence_items():
    evidence = [_item(i) for i in range(PROMPT_EVIDENCE_MAX + 3)]
    prompt = _build_system_prompt(slim_agent(evidence=evidence), [])

    assert prompt.count("<evidence ") == PROMPT_EVIDENCE_MAX


def test_evidence_id_cannot_break_the_fence():
    prompt = _build_system_prompt(slim_agent(evidence=[_item(1, item_id='e1"><x>')]), [])

    assert "<x>" not in prompt
    assert '<evidence id="e1x"' in prompt


def test_prompt_states_the_stance_and_strength():
    prompt = _build_system_prompt(slim_agent(strength=0.25), [])

    assert "POSITIVE (strength 0.25)" in prompt
