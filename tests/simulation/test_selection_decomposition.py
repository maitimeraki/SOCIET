"""P4-T4 — the selection re-run over the Document-first evidence shape.

One logical candidate set, two evidence shapes: the pre-P4-A rows ("before" —
objects whose `.properties` carry only the flat `chunk_id`/`chunk_ids`, mapping
rows with `total_relevance`/`evidence_nodes`) and the shape live graphs produce
after the Document-first model ("after" — `.properties` carrying
`triplet_source_id` plus `document_anchor`, mapping rows carrying
`document_anchor`).

The two properties pinned here are the P4-T4 acceptance:
  * the numbers hold — semantic / density / blended are identical across the
    shapes, so the Document model moved the evidence, not the scores;
  * the "after" anchors are a strict superset — the same chunk ids now arrive
    through `triplet_source_id`, plus the `document_anchor` document joins —
    and they reach the caller-owned S9 `selection_rows` sink intact.

Reverting the Document-model reads in the one adapter (`_evidence_row`) makes
the anchor assertions here fail; the numbers-hold assertion is deliberately
shape-independent.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.persona.models_persona import PersonaIdentity
from src.simulation.debate_config import DebateConfig
from src.simulation.profile_synthesizer import ProfileSynthesizer
from src.simulation.relevance_matrix import SelectionCandidate, rank_candidates
from src.utils.queryIntend import QueryIntent

_INTENT = QueryIntent(direct_keywords=["carbon", "tax"], latent_sectors=[], search_perspectives=[])
_CONFIG = DebateConfig()

# The semantic text is a property of the candidate, not of its evidence shape.
_TEXT = {"Carbon Analyst": "carbon tax policy", "Grid Engineer": "grid engineering"}


class _Entity:
    """Stands in for a debate-path EntityNode: id, name, properties, score."""

    def __init__(self, id=None, name=None, score: float = 1.0, properties=None):
        self.id = id
        self.name = name
        self.relevance_score = score
        self.properties = properties or {}
        self.domain_tags = []
        self.summary = ""
        self.label = "Persona"


def _before_evidence() -> dict[str, list]:
    """The pre-P4-A row shape: flat `chunk_id`/`chunk_ids`, no document refs."""
    return {
        "Carbon Analyst": [
            _Entity(id="e-1", name="Carbon Analyst", score=2.0, properties={"chunk_id": "node-7"}),
            {"total_relevance": 0.5, "evidence_nodes": ["Peer Sector"]},
        ],
        "Grid Engineer": [
            _Entity(id="e-2", name="Grid Engineer", score=1.0, properties={"chunk_ids": ["node-9", "node-9"]}),
        ],
    }


def _after_evidence() -> dict[str, list]:
    """The post-P4-A shape: `triplet_source_id` + `document_anchor`, same nodes."""
    return {
        "Carbon Analyst": [
            _Entity(id="e-1", name="Carbon Analyst", score=2.0,
                    properties={"triplet_source_id": "node-7", "document_anchor": "doc-1"}),
            {"total_relevance": 0.5, "evidence_nodes": ["Peer Sector"], "document_anchor": "doc-1"},
        ],
        "Grid Engineer": [
            _Entity(id="e-2", name="Grid Engineer", score=1.0,
                    properties={"triplet_source_id": "node-9", "document_anchor": "doc-2"}),
        ],
    }


def _run(shape) -> list:
    candidates = [
        SelectionCandidate(name=name, text=_TEXT[name], evidence=evidence)
        for name, evidence in shape().items()
    ]
    return rank_candidates(candidates, _INTENT, _CONFIG)


def _by_name(rows) -> dict:
    return {row.name: row for row in rows}


def _anchor_keys(anchors) -> set:
    return {(anchor["kind"], anchor.get("id"), anchor.get("name")) for anchor in anchors}


def test_numbers_hold_across_the_before_and_after_evidence_shapes():
    """The Document model moved the evidence, not the scores."""
    before, after = _by_name(_run(_before_evidence)), _by_name(_run(_after_evidence))

    assert list(before) == list(after) == ["Carbon Analyst", "Grid Engineer"]
    for name in before:
        assert after[name].semantic == pytest.approx(before[name].semantic)
        assert after[name].density == pytest.approx(before[name].density)
        assert after[name].blended == pytest.approx(before[name].blended)

    # density is still the raw-sum normalization (2.5 vs 1.0) over the same scores
    assert after["Carbon Analyst"].density == pytest.approx(1.0)
    assert after["Grid Engineer"].density == pytest.approx(0.4)
    for row in after.values():
        assert row.blended == pytest.approx(_CONFIG.w1 * row.semantic + _CONFIG.w2 * row.density)


def test_after_anchors_are_a_strict_superset_from_the_document_model():
    """Same chunk nodes via `triplet_source_id`, plus the `document_anchor` joins."""
    before, after = _by_name(_run(_before_evidence)), _by_name(_run(_after_evidence))

    for name in before:
        assert _anchor_keys(before[name].anchors) < _anchor_keys(after[name].anchors)

    assert after["Carbon Analyst"].anchors == (
        {"kind": "node", "id": "e-1", "name": "Carbon Analyst"},
        {"kind": "chunk", "id": "node-7"},       # .properties["triplet_source_id"]
        {"kind": "document", "id": "doc-1"},     # .properties["document_anchor"]
        {"kind": "node", "name": "Peer Sector"},  # the mapping row's evidence node
    )
    assert after["Grid Engineer"].anchors == (
        {"kind": "node", "id": "e-2", "name": "Grid Engineer"},
        {"kind": "chunk", "id": "node-9"},
        {"kind": "document", "id": "doc-2"},
    )
    # the chunk ids the pre-P4-A rows carried are the same nodes the Document
    # model now surfaces — no id is invented or dropped on the way over
    assert before["Grid Engineer"].anchors == (
        {"kind": "node", "id": "e-2", "name": "Grid Engineer"},
        {"kind": "chunk", "id": "node-9"},
    )


def _after_entities() -> list:
    return [
        _Entity(id="e-1", name="Carbon Analyst", score=2.0,
                properties={"triplet_source_id": "node-7", "document_anchor": "doc-1"}),
        _Entity(id="e-2", name="Grid Engineer", score=1.0,
                properties={"triplet_source_id": "node-9", "document_anchor": "doc-2"}),
    ]


def _synth(entities) -> ProfileSynthesizer:
    """A synthesizer stub in the shape of tests/simulation/test_profile_synthesizer.py."""
    async def build_profile(**kwargs):
        return MagicMock(identity=PersonaIdentity(
            name=kwargs["agent_name"], archetype="Analyst", communication_style="factual"))

    repo = MagicMock()
    repo.fetch_nodes_by_names = AsyncMock(return_value={})
    repo.calculate_agent_metrics_and_context_for_llm = AsyncMock(return_value={})
    repo.build_single_agent_profile_from_node = AsyncMock(side_effect=build_profile)

    ctx = MagicMock()
    ctx.find_relevant_entities = AsyncMock(return_value=entities)
    return ProfileSynthesizer(persona_repo=repo, graph_context=ctx)


@pytest.mark.asyncio
async def test_selection_rows_flow_through_synthesize_with_document_model_anchors():
    """The S9 slot carries the decomposition with the Document-model anchors."""
    rows: list = []

    profiles = await _synth(_after_entities()).synthesize(
        query="Should we tax carbon?", dataset_id="ds", max_agents=2,
        intent=_INTENT, config=_CONFIG, selection_rows=rows,
    )

    assert [row.name for row in rows] == ["Carbon Analyst", "Grid Engineer"]
    assert [p.identity.name for p in profiles] == ["Carbon Analyst", "Grid Engineer"]
    top = rows[0]
    assert {"kind": "chunk", "id": "node-7"} in top.anchors
    assert {"kind": "document", "id": "doc-1"} in top.anchors
    assert top.blended == pytest.approx(_CONFIG.w1 * top.semantic + _CONFIG.w2 * top.density)
