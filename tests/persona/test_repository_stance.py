"""Graph-derived stance: the deterministic fallback and the distilled precedence.

Base `__Entity__` nodes almost never carry `stance`/`conviction`/`cior`, so
every synthesized agent collapsed to NEUTRAL with cior 0.0. These tests pin the
deterministic derivation (from `OPPOSES`/`SUPPORTS` relation evidence) and the
distilled-stance precedence that removes the collapse.
"""
from unittest.mock import AsyncMock

import pytest

from src.persona.agent import Stance
from src.persona.repository import PersonaRepository


def _repo(llm_client=None) -> PersonaRepository:
    """A repository with no driver — the existing no-database seam."""
    repo = PersonaRepository.__new__(PersonaRepository)
    repo.get_provenance = AsyncMock(return_value=[])
    if llm_client is not None:
        repo.llm_client = llm_client
    return repo


async def _build(repo, distilled=None, **node) -> object:
    """Build one Agent through the real build path (no DB on the mocked seam)."""
    return await repo.build_single_agent_profile_from_node(
        agent_name=str(node.get("name", "X")),
        node=node,
        user_query="Should we do it?",
        dataset_id="ds",
        agent_metrics={},
        sector_results=[],
        llm_output=None,
        distilled=distilled,
    )



def test_opposes_evidence_derives_a_negative_stance():
    """A node that opposes something is NEGATIVE, not the NEUTRAL collapse."""
    node = {"name": "Critic", "relations": ["OPPOSES", "OPPOSES"]}

    stance, conviction, cior = _repo()._derive_stance(node)

    assert stance is Stance.NEGATIVE
    assert 0.0 <= conviction <= 1.0 and conviction > 0.0
    assert -1.0 <= cior <= 1.0 and cior < 0.0


def test_supports_evidence_derives_a_positive_stance():
    node = {"name": "Champion", "relations": ["SUPPORTS", "SUPPORTS", "SUPPORTS"]}

    stance, conviction, cior = _repo()._derive_stance(node)

    assert stance is Stance.POSITIVE
    assert 0.0 <= conviction <= 1.0
    assert cior > 0.0


def test_conflicting_evidence_derives_an_ambivalent_stance():
    node = {"name": "Torn", "relations": ["OPPOSES", "SUPPORTS"]}

    stance, conviction, cior = _repo()._derive_stance(node)

    assert stance is Stance.AMBIVALENT
    assert -1.0 <= cior <= 1.0 and cior == 0.0


def test_more_evidence_raises_conviction():
    """Conviction scales with how much relation evidence the node carries."""
    weak = _repo()._derive_stance({"name": "w", "relations": ["OPPOSES"]})
    strong = _repo()._derive_stance({"name": "s", "relations": ["OPPOSES"] * 4})

    assert weak[1] < strong[1] == pytest.approx(1.0)


def test_no_relation_evidence_derives_nothing():
    """No evidence → None, so the caller keeps its existing safe default."""
    assert _repo()._derive_stance({"name": "Bare"}) is None


def test_effective_stance_prefers_the_derivation_over_a_node_property():
    """The shared precedence: distilled → derivation → node property.

    A node carrying both a `stance` property and OPPOSES evidence derives
    NEGATIVE — the same value the build and the synthesizer's persistence use,
    so `Agent.stance` and `Persona.stance` cannot disagree.
    """
    node = {"name": "Torn", "stance": "POSITIVE", "relations": ["OPPOSES"]}

    assert _repo()._effective_stance(node, {})[0] is Stance.NEGATIVE


@pytest.mark.asyncio
async def test_build_uses_the_graph_derivation_when_not_distilled():
    """Step 5: with no distilled stance, the node's OPPOSES evidence decides."""
    agent = await _build(_repo(), None, name="Critic", domain_tags=["risk"], relations=["OPPOSES"])

    assert agent.stance is Stance.NEGATIVE
    assert agent.cior < 0.0


@pytest.mark.asyncio
async def test_build_reads_relation_evidence_from_the_metrics():
    """Live path: the node has no edges, but the metrics' recent memories do."""
    repo = _repo()
    agent = await repo.build_single_agent_profile_from_node(
        agent_name="Champion", node={"name": "Champion", "domain_tags": ["growth"]},
        user_query="q", dataset_id="ds",
        agent_metrics={"recent_memories": [{"relation_type": "SUPPORTS"}]},
        sector_results=[], llm_output=None,
    )

    assert agent.stance is Stance.POSITIVE


@pytest.mark.asyncio
async def test_distilled_stance_beats_the_graph_derivation():
    from src.persona.repository import DistilledProfile

    agent = await _build(
        _repo(),
        DistilledProfile("d", "p", Stance.POSITIVE, 0.9, 0.7),
        name="Torn", domain_tags=["x"], relations=["OPPOSES"],
    )

    assert agent.stance is Stance.POSITIVE
    assert agent.cior == pytest.approx(0.7)


class _SpyClient:
    """Duck-typed LLM client returning a fixed reply."""

    def __init__(self, reply: str):
        self._reply = reply

    async def generate(self, **kwargs) -> str:
        return self._reply


_REPLY = (
    "PERSONA: Optimist\nDESCRIPTION: d1\nPERSPECTIVE: p1\nSTANCE: POSITIVE | 0.8 | 0.6\n"
    "PERSONA: Skeptic\nDESCRIPTION: d2\nPERSPECTIVE: p2\nSTANCE: NEGATIVE | 0.9 | -0.7\n"
    "PERSONA: Referee\nDESCRIPTION: d3\nPERSPECTIVE: p3\nSTANCE: NEUTRAL | 0.3 | 0.0\n"
)


@pytest.mark.asyncio
async def test_a_distilled_roster_is_not_uniformly_neutral_and_cior_varies():
    """THE acceptance test: distinct distilled stances survive into the roster."""
    repo = _repo(_SpyClient(_REPLY))
    names = ("Optimist", "Skeptic", "Referee")

    distilled = await repo.distill_profiles(
        personas=[{"name": name} for name in names],
        query="Should we expand?",
        stance_axis="Support = expand; oppose = stay.",
    )
    roster = [await _build(repo, distilled[name], name=name, domain_tags=["strategy"]) for name in names]

    stances = [agent.stance for agent in roster]
    assert stances != [Stance.NEUTRAL] * len(roster)
    assert Stance.POSITIVE in stances and Stance.NEGATIVE in stances
    assert len({agent.cior for agent in roster}) > 1
    assert all(-1.0 <= agent.cior <= 1.0 for agent in roster)


@pytest.mark.asyncio
async def test_distill_falls_back_to_the_graph_derivation_when_the_stance_line_is_missing():
    """Step 6: a parsed block with no STANCE line still gets a derived stance + a warning."""
    repo = _repo(_SpyClient("PERSONA: X\nDESCRIPTION: d\nPERSPECTIVE: p\n"))
    warnings: list[str] = []

    out = await repo.distill_profiles(
        personas=[{"name": "X", "node": {"name": "X", "relations": ["OPPOSES"]}}],
        query="q", stance_axis="Support = yes.", warnings=warnings,
    )

    assert out["X"].stance is Stance.NEGATIVE
    assert any("STANCE" in w for w in warnings)


@pytest.mark.asyncio
async def test_distill_parses_the_stance_line_into_the_returned_value():
    repo = _repo(_SpyClient(_REPLY))

    out = await repo.distill_profiles(
        personas=[{"name": "Optimist"}], query="q",
    )

    assert out["Optimist"].stance is Stance.POSITIVE
    assert out["Optimist"].conviction == pytest.approx(0.8)
    assert out["Optimist"].cior == pytest.approx(0.6)

