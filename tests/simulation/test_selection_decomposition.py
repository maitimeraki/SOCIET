"""P4-T4 — the selection re-run over the Document-first evidence shape.

One production candidate set, two adapter read sets. Production entity rows are
the extractor's properties plus `triplet_source_id` (llama-index writes it) and
`/hatch` sector rows are mappings with `total_relevance`/`evidence_nodes` —
identical before and after P4-A. What P4-A changed is the *adapter*: the retired
`_evidence_row` never read `triplet_source_id`, the shipped one does, so the
same rows now surface their source chunk node ids as anchors. The recorded
before/after difference is therefore "the adapter gained the read", not "the
graph changed".

No `document_anchor` appears on entity or sector rows: nothing writes it there
(the Document model writes it into *chunk* metadata, `graph_build.py`), so the
document-anchor read is exercised separately below as the tolerant read it is —
never as a production shape.

The two properties pinned here are the P4-T4 acceptance:
  * the numbers hold — semantic / density / blended are identical under both
    read sets, so the Document model moved the evidence, not the scores;
  * the shipped anchors are a strict superset of the retired ones — the same
    chunk node ids now arrive through `triplet_source_id` — and they reach the
    caller-owned S9 `selection_rows` sink intact.

Reverting the `triplet_source_id` read in the one adapter (`_evidence_row`)
makes the anchor assertions here fail; the numbers-hold assertion is
deliberately read-set-independent.
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


def _production_evidence() -> dict[str, list]:
    """The row shape production produces on both sides of P4-A.

    Entity `.properties` are `{extractor output} ∪ {triplet_source_id}` — no
    `document_anchor`, no `document_ids`, no flat `chunk_id`/`chunk_ids` — plus
    a `/hatch`-style mapping row.
    """
    return {
        "Carbon Analyst": [
            _Entity(id="e-1", name="Carbon Analyst", score=2.0,
                    properties={"triplet_source_id": "node-7"}),
            {"total_relevance": 0.5, "evidence_nodes": ["Peer Sector"]},
        ],
        "Grid Engineer": [
            _Entity(id="e-2", name="Grid Engineer", score=1.0,
                    properties={"triplet_source_id": "node-9"}),
        ],
    }


def _retired_evidence() -> dict[str, list]:
    """The same production rows as the retired adapter's reads could see them.

    The graph rows were the same; the retired `_evidence_row` never read
    `triplet_source_id`, so stripping that key reproduces exactly the anchors it
    could surface. Nothing else is removed: the mapping rows are read the same
    way on both sides.
    """
    out: dict[str, list] = {}
    for name, evidence in _production_evidence().items():
        rows = []
        for item in evidence:
            if isinstance(item, _Entity):
                rows.append(_Entity(
                    id=item.id, name=item.name, score=item.relevance_score,
                    properties={k: v for k, v in item.properties.items()
                                if k != "triplet_source_id"},
                ))
            else:
                rows.append(dict(item))
        out[name] = rows
    return out


def _run(evidence: dict[str, list]) -> list:
    candidates = [
        SelectionCandidate(name=name, text=_TEXT[name], evidence=rows)
        for name, rows in evidence.items()
    ]
    return rank_candidates(candidates, _INTENT, _CONFIG)


def _by_name(rows) -> dict:
    return {row.name: row for row in rows}


def _anchor_keys(anchors) -> set:
    return {(anchor["kind"], anchor.get("id"), anchor.get("name")) for anchor in anchors}


def test_numbers_hold_across_the_retired_and_shipped_read_sets():
    """The Document model moved the evidence, not the scores."""
    before, after = _by_name(_run(_retired_evidence())), _by_name(_run(_production_evidence()))

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


def test_the_shipped_adapter_gained_the_triplet_source_id_read():
    """Same rows, same chunk nodes — the anchors now arrive via `triplet_source_id`."""
    before, after = _by_name(_run(_retired_evidence())), _by_name(_run(_production_evidence()))

    for name in before:
        assert _anchor_keys(before[name].anchors) < _anchor_keys(after[name].anchors)

    assert after["Carbon Analyst"].anchors == (
        {"kind": "node", "id": "e-1", "name": "Carbon Analyst"},
        {"kind": "chunk", "id": "node-7"},        # .properties["triplet_source_id"]
        {"kind": "node", "name": "Peer Sector"},  # the mapping row's evidence node
    )
    assert after["Grid Engineer"].anchors == (
        {"kind": "node", "id": "e-2", "name": "Grid Engineer"},
        {"kind": "chunk", "id": "node-9"},
    )
    # the retired reads saw the same nodes but no chunk refs at all
    assert before["Grid Engineer"].anchors == (
        {"kind": "node", "id": "e-2", "name": "Grid Engineer"},
    )


def test_document_anchor_reads_are_tolerant_not_a_production_shape():
    """Tolerance, not production: nothing writes `document_anchor` on these rows.

    The Document model writes it into *chunk* metadata only, so no entity or
    sector row carries it today. The adapter must still surface one if a row
    ever does — that is all this pins.
    """
    entity = _Entity(id="e-9", name="Tolerant", score=1.0,
                     properties={"triplet_source_id": "node-9", "document_anchor": "doc-9"})
    rows = rank_candidates(
        [SelectionCandidate(name="Tolerant", text="t", evidence=[entity])], _INTENT, _CONFIG,
    )
    assert {"kind": "document", "id": "doc-9"} in rows[0].anchors

    # the mapping-row half of the same tolerant read
    sector = {"total_relevance": 1.0, "evidence_nodes": ["S"], "document_ids": ["doc-10"]}
    rows = rank_candidates(
        [SelectionCandidate(name="S", text="t", evidence=[sector])], _INTENT, _CONFIG,
    )
    assert {"kind": "document", "id": "doc-10"} in rows[0].anchors


def _production_entities() -> list:
    return [
        _Entity(id="e-1", name="Carbon Analyst", score=2.0,
                properties={"triplet_source_id": "node-7"}),
        _Entity(id="e-2", name="Grid Engineer", score=1.0,
                properties={"triplet_source_id": "node-9"}),
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
async def test_selection_rows_flow_through_synthesize_with_the_document_model_anchors():
    """The S9 slot carries the decomposition with the Document-model chunk anchors."""
    rows: list = []

    profiles = await _synth(_production_entities()).synthesize(
        query="Should we tax carbon?", dataset_id="ds", max_agents=2,
        intent=_INTENT, config=_CONFIG, selection_rows=rows,
    )

    assert [row.name for row in rows] == ["Carbon Analyst", "Grid Engineer"]
    assert [p.identity.name for p in profiles] == ["Carbon Analyst", "Grid Engineer"]
    top = rows[0]
    assert {"kind": "chunk", "id": "node-7"} in top.anchors
    assert top.blended == pytest.approx(_CONFIG.w1 * top.semantic + _CONFIG.w2 * top.density)
