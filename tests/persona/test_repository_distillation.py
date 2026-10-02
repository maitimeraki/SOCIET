"""S5: ONE batched distillation call for the whole selection set (P3-T1/T2).

The repository is built with `__new__` (the existing no-database seam) so these
tests never touch Neo4j or the embedding model.
"""
import pytest

from src.persona.repository import PersonaRepository


class _SpyClient:
    """Duck-typed LLM client that records every `generate(...)` call it receives."""

    def __init__(self, reply):
        self.calls = []
        self._reply = reply

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self._reply, Exception):
            raise self._reply
        return self._reply


def _repo(llm_client=None) -> PersonaRepository:
    """A repository with no driver; `llm_client` only when one is passed."""
    repo = PersonaRepository.__new__(PersonaRepository)
    if llm_client is not None:
        repo.llm_client = llm_client
    return repo


def _entry(name: str, *, summary: str = "", tags=(), anchors=()) -> dict:
    """One persona entry in the shape ProfileSynthesizer hands the batch call."""
    return {
        "name": name,
        "node": {"name": name, "domain_tags": list(tags)},
        "sector_results": [{"domain_tag": tags[0]}] if tags else [],
        "evidence": [summary] if summary else [],
        "anchors": [dict(anchor) for anchor in anchors],
    }


_REPLY_TWO = (
    "PERSONA: Alice\nDESCRIPTION: Alice's one-liner.\nPERSPECTIVE: I am Alice. I weigh the evidence.\n"
    "PERSONA: Bob\nDESCRIPTION: Bob's one-liner.\nPERSPECTIVE: I am Bob. I follow the grid.\n"
)


@pytest.mark.asyncio
async def test_one_batch_call_carries_every_persona():
    client = _SpyClient(_REPLY_TWO)
    repo = _repo(client)

    out = await repo.distill_profiles(
        personas=[_entry("Alice"), _entry("Bob")],
        query="Should we tax carbon?",
    )

    assert len(client.calls) == 1  # ONE call for the whole selection set
    call = client.calls[0]
    assert set(call) == {"system_prompt", "user_prompt"}  # the generate(...) contract
    assert "PERSONA: Alice" in call["user_prompt"]
    assert "PERSONA: Bob" in call["user_prompt"]
    assert out["Alice"] == ("Alice's one-liner.", "I am Alice. I weigh the evidence.")
    assert out["Bob"] == ("Bob's one-liner.", "I am Bob. I follow the grid.")


@pytest.mark.asyncio
async def test_prompt_carries_question_context_anchors_and_grounding():
    """P3-T2: the S3 stance axis + core question + the S4 anchors are in the prompt."""
    client = _SpyClient("PERSONA: Alice\nDESCRIPTION: d.\nPERSPECTIVE: p.\n")
    repo = _repo(client)

    await repo.distill_profiles(
        personas=[_entry(
            "Alice",
            summary="carbon tax evidence",
            tags=["economics"],
            anchors=[{"kind": "node", "id": "n1", "name": "Alice"}, {"kind": "chunk", "id": "c1"}],
        )],
        query="Should we tax carbon?",
        core_question="Is a carbon tax wise?",
        stance_axis="Support = tax carbon; oppose = no tax.",
    )

    prompt = client.calls[0]["user_prompt"]
    assert "Is a carbon tax wise?" in prompt
    assert "Support = tax carbon; oppose = no tax." in prompt
    assert "node:n1" in prompt and "chunk:c1" in prompt
    assert "carbon tax evidence" in prompt and "economics" in prompt


@pytest.mark.asyncio
async def test_two_intents_produce_two_different_prompts():
    """The same graph + two intents → the distillation prompt differs accordingly."""
    client = _SpyClient("PERSONA: Alice\nDESCRIPTION: d.\nPERSPECTIVE: p.\n")
    repo = _repo(client)

    await repo.distill_profiles(
        personas=[_entry("Alice")], query="q",
        core_question="Tax carbon?", stance_axis="Support = tax carbon.",
    )
    await repo.distill_profiles(
        personas=[_entry("Alice")], query="q",
        core_question="Expand to Europe?", stance_axis="Support = expand.",
    )

    first, second = client.calls[0]["user_prompt"], client.calls[1]["user_prompt"]
    assert first != second
    assert "Tax carbon?" in first and "Tax carbon?" not in second
    assert "Expand to Europe?" in second


@pytest.mark.asyncio
async def test_unparseable_persona_falls_back_to_template_and_warns():
    """A persona missing from the reply gets the template; the rest are distilled."""
    client = _SpyClient(
        "PERSONA: Alice\nDESCRIPTION: Alice distilled.\nPERSPECTIVE: I am Alice.\n"
        "PERSONA: Carol\n"  # empty block → nothing parseable
    )
    repo = _repo(client)
    warnings: list[str] = []

    out = await repo.distill_profiles(
        personas=[
            _entry("Alice"),
            _entry("Bob", summary="Bob works on grids.", tags=["energy"]),
            _entry("Carol"),
        ],
        query="q",
        warnings=warnings,
    )

    assert out["Alice"] == ("Alice distilled.", "I am Alice.")
    assert out["Bob"][0].startswith("Bob:")  # deterministic template
    assert "energy" in out["Bob"][1]
    assert out["Carol"][0].startswith("Carol:")
    assert len(warnings) == 2  # one per failed persona, each naming it
    assert any("Bob" in w for w in warnings) and any("Carol" in w for w in warnings)
    assert all("deterministic template" in w for w in warnings)


@pytest.mark.asyncio
async def test_whole_call_failure_falls_back_every_persona_with_one_warning():
    client = _SpyClient(RuntimeError("provider down"))
    repo = _repo(client)
    warnings: list[str] = []

    out = await repo.distill_profiles(
        personas=[_entry("Alice"), _entry("Bob")], query="q", warnings=warnings,
    )

    assert set(out) == {"Alice", "Bob"}
    assert out["Alice"][0].startswith("Alice:") and out["Bob"][0].startswith("Bob:")
    assert len(warnings) == 1
    assert "provider down" in warnings[0] and "2 personas" in warnings[0]


@pytest.mark.asyncio
async def test_no_client_falls_back_every_persona_with_one_warning():
    repo = _repo(None)
    warnings: list[str] = []

    out = await repo.distill_profiles(
        personas=[_entry("Alice")], query="q", warnings=warnings,
    )

    assert out["Alice"][0].startswith("Alice:")
    assert len(warnings) == 1 and "no LLM client" in warnings[0]


@pytest.mark.asyncio
async def test_empty_selection_makes_no_call_and_no_warning():
    client = _SpyClient("unused")
    repo = _repo(client)
    warnings: list[str] = []

    assert await repo.distill_profiles(personas=[], query="q", warnings=warnings) == {}
    assert client.calls == [] and warnings == []
