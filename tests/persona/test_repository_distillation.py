"""S5: ONE batched distillation call for the whole selection set (P3-T1/T2).

The repository is built with `__new__` (the existing no-database seam) so these
tests never touch Neo4j or the embedding model.
"""

import pytest

from src.persona.agent import Stance
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
    assert (out["Alice"].description, out["Alice"].perspective) == (
        "Alice's one-liner.",
        "I am Alice. I weigh the evidence.",
    )
    assert (out["Bob"].description, out["Bob"].perspective) == (
        "Bob's one-liner.",
        "I am Bob. I follow the grid.",
    )


@pytest.mark.asyncio
async def test_prompt_carries_question_context_anchors_and_grounding():
    """P3-T2: the S3 stance axis + core question + the S4 anchors are in the prompt."""
    client = _SpyClient("PERSONA: Alice\nDESCRIPTION: d.\nPERSPECTIVE: p.\n")
    repo = _repo(client)

    await repo.distill_profiles(
        personas=[
            _entry(
                "Alice",
                summary="carbon tax evidence",
                tags=["economics"],
                anchors=[
                    {"kind": "node", "id": "n1", "name": "Alice"},
                    {"kind": "chunk", "id": "c1"},
                ],
            )
        ],
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
        personas=[_entry("Alice")],
        query="q",
        core_question="Tax carbon?",
        stance_axis="Support = tax carbon.",
    )
    await repo.distill_profiles(
        personas=[_entry("Alice")],
        query="q",
        core_question="Expand to Europe?",
        stance_axis="Support = expand.",
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

    assert (out["Alice"].description, out["Alice"].perspective) == (
        "Alice distilled.",
        "I am Alice.",
    )
    assert out["Bob"].description.startswith("Bob:")  # deterministic template
    assert "energy" in out["Bob"].perspective
    assert out["Carol"].description.startswith("Carol:")
    # Bob + Carol had no parseable block (template); Alice's block parsed but
    # carried no STANCE line (deterministic derivation) — each names its persona.
    assert len(warnings) == 3
    assert any("Bob" in w for w in warnings) and any("Carol" in w for w in warnings)
    assert any("Alice" in w and "STANCE" in w for w in warnings)
    assert sum("deterministic template" in w for w in warnings) == 2


@pytest.mark.asyncio
async def test_whole_call_failure_falls_back_every_persona_with_one_warning():
    client = _SpyClient(RuntimeError("provider down"))
    repo = _repo(client)
    warnings: list[str] = []

    out = await repo.distill_profiles(
        personas=[_entry("Alice"), _entry("Bob")],
        query="q",
        warnings=warnings,
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
        personas=[_entry("Alice")],
        query="q",
        warnings=warnings,
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


"""Task 4: the distillation carries the persona's full identity, not just a voice."""


def test_distilled_profile_carries_identity():
    from src.persona.repository import DistilledProfile

    d = DistilledProfile(
        "desc",
        "persp",
        archetype="Regulator",
        communication_style="formal and cautious",
    )

    assert d.archetype == "Regulator"
    assert d.communication_style == "formal and cautious"


def test_identity_fields_are_appended_after_cior():
    """The NamedTuple is built positionally at three sites — new fields go last."""
    from src.persona.repository import DistilledProfile

    assert DistilledProfile._fields[:5] == (
        "description",
        "perspective",
        "stance",
        "conviction",
        "cior",
    )
    # Every identity field is defaulted, so the 2- and 5-arg positional calls survive.
    assert DistilledProfile("d", "p")[5:] == (None,) * 7


_REPLY_IDENTITY = (
    "PERSONA: Alice\n"
    "DESCRIPTION: Alice's one-liner.\n"
    "ARCHETYPE: Regulator\n"
    "COMMUNICATION STYLE: formal and cautious\n"
    "EXPERTISE: Operational\n"
    "DOMAIN TAGS: banking, compliance\n"
    "BELIEF: Markets self-correct when the rules are stable.\n"
    "OPINION: The tax is workable if phased in.\n"
    "PERSPECTIVE: I am Alice. I weigh the evidence.\n"
    "STANCE: POSITIVE | 0.7 | 0.4\n"
)


@pytest.mark.asyncio
async def test_identity_fields_are_parsed_from_the_block():
    client = _SpyClient(_REPLY_IDENTITY)
    repo = _repo(client)

    out = await repo.distill_profiles(personas=[_entry("Alice")], query="q")

    alice = out["Alice"]
    assert alice.archetype == "Regulator"
    assert alice.communication_style == "formal and cautious"
    assert alice.expertise_level == "Operational"
    assert alice.domain_tags == ["banking", "compliance"]
    assert alice.belief == "Markets self-correct when the rules are stable."
    assert alice.opinion == "The tax is workable if phased in."
    assert (alice.description, alice.perspective) == (
        "Alice's one-liner.",
        "I am Alice. I weigh the evidence.",
    )
    assert (alice.stance, alice.conviction, alice.cior) == (Stance.POSITIVE, 0.7, 0.4)


@pytest.mark.asyncio
async def test_identity_lines_parse_out_of_prompt_order():
    """A reply that appends BELIEF/OPINION after PERSPECTIVE still parses."""
    client = _SpyClient(
        "PERSONA: Alice\nDESCRIPTION: d.\nPERSPECTIVE: I am Alice.\n"
        "BELIEF: Rules beat discretion.\nSTANCE: NEGATIVE | 0.6 | -0.5\n"
    )
    repo = _repo(client)

    alice = (await repo.distill_profiles(personas=[_entry("Alice")], query="q"))[
        "Alice"
    ]

    assert alice.perspective == "I am Alice."
    assert alice.belief == "Rules beat discretion."
    assert (alice.stance, alice.conviction, alice.cior) == (Stance.NEGATIVE, 0.6, -0.5)


@pytest.mark.asyncio
async def test_template_derives_archetype_from_the_node_type():
    repo = _repo(None)
    entry = _entry("Alice")
    entry["node"]["label"] = "Regulator"

    out = await repo.distill_profiles(personas=[entry], query="q")

    assert out["Alice"].archetype == "Regulator"
