"""Phase-2 golden path (design acceptance criterion §13.3 — bugs 3 & 4).

Two entity nodes of DIFFERENT real types ("Company", "Regulator") must yield two
Agents whose `identity.archetype` differ and neither equals the erased
"Strategic Analyst" constant, and whose `bio` is grounded in that node's own
source snippet — not the other node's, and not a shared constant.

Approach: the public seam. `ProfileSynthesizer.synthesize(distill=True)` runs
against a bare `PersonaRepository` instance carrying the REAL
`build_single_agent_profile_from_node` / `fetch_source_evidence_by_chunk` (backed
by a stub driver) with only the external I/O stubbed. So the whole path is
exercised: roster selection → label bridging → the build's identity precedence →
per-persona distillation reaching its own `bio`.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.persona.repository import DistilledProfile, PersonaRepository
from src.simulation.profile_synthesizer import ProfileSynthesizer


def _entity(name: str, label: str, score: float, chunk_id: str, tag: str) -> MagicMock:
    """A graph entity node carrying its real type label and its own chunk ref."""
    node = MagicMock()
    node.id = name
    node.name = name
    node.label = label
    node.properties = {"name": name, "triplet_source_id": chunk_id, "domain_tags": [tag]}
    node.relevance_score = score
    node.domain_tags = [tag]
    node.summary = f"{name} summary"
    return node


def _chunk_driver(rows: list[dict]) -> MagicMock:
    """A stub Neo4j driver whose one query returns `rows` (chunk_id + text)."""
    result = MagicMock()
    result.data = AsyncMock(return_value=rows)
    session = MagicMock()
    session.run = AsyncMock(return_value=result)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session_cm)
    return driver


def _golden_repo(snippets_by_chunk: dict[str, str]) -> PersonaRepository:
    """A bare repo with the REAL build + chunk fetch, everything external stubbed."""
    repo = PersonaRepository.__new__(PersonaRepository)
    repo._db = "neo4j"
    repo._driver = _chunk_driver(
        [{"chunk_id": cid, "text": text} for cid, text in snippets_by_chunk.items()]
    )
    # External I/O only; the node fallback uses each representative's properties.
    repo.fetch_nodes_by_names = AsyncMock(return_value={})
    repo.calculate_agent_metrics_and_context_for_llm = AsyncMock(return_value={})
    repo.write_persona_provenance = AsyncMock(return_value=1)
    repo.write_persona_entity_links = AsyncMock(return_value=1)
    repo.get_provenance = AsyncMock(return_value=[])

    async def _distill(personas, **kwargs):
        # Ground each persona's voice in the snippet its OWN evidence carried —
        # a schema-less stand-in for the LLM that echoes the persona's grounding.
        return {
            p["name"]: DistilledProfile(
                description=p["evidence"][0] if p["evidence"] else p["name"],
                perspective=f"I am {p['name']}.",
            )
            for p in personas
        }

    repo.distill_profiles = AsyncMock(side_effect=_distill)
    return repo


class _RosterContext:
    """A GraphContext stand-in exposing only the seed fetch (traversal absent)."""

    def __init__(self, entities):
        self._entities = entities

    async def find_relevant_entities(self, query, limit=10):
        return self._entities


_COMPANY = _entity("Acme Bank", "Company", 0.9, "c1", "retail")
_REGULATOR = _entity("Bank Authority", "Regulator", 0.8, "c2", "banking")
_SNIPPETS = {
    "c1": "Acme Bank acquired a fintech startup for $2.5B.",
    "c2": "The Bank Authority fined three lenders for mis-selling.",
}


@pytest.mark.asyncio
async def test_distinct_archetypes_and_grounded_bio():
    repo = _golden_repo(_SNIPPETS)
    synth = ProfileSynthesizer(repo, _RosterContext([_COMPANY, _REGULATOR]))

    profiles = await synth.synthesize(
        query="Should we expand into Europe?", dataset_id="ds", max_agents=2, distill=True,
    )

    assert [p.identity.name for p in profiles] == ["Acme Bank", "Bank Authority"]
    by_name = {p.identity.name: p for p in profiles}

    # Bug 3: two real types → two distinct archetypes, never the erased constant.
    archetypes = {p.identity.archetype for p in profiles}
    assert archetypes == {"Company", "Regulator"}
    assert len(archetypes) == 2  # they differ
    assert "Strategic Analyst" not in archetypes

    # Bug 4: each bio quotes that node's own source snippet — not the other's.
    assert "fintech startup" in by_name["Acme Bank"].bio
    assert "mis-selling" not in by_name["Acme Bank"].bio
    assert "mis-selling" in by_name["Bank Authority"].bio
    assert "fintech startup" not in by_name["Bank Authority"].bio

    # Domain tags derive from each node, not a shared constant.
    assert by_name["Acme Bank"].domain_tags == ["retail"]
    assert by_name["Bank Authority"].domain_tags == ["banking"]
