import pytest
from pydantic import ValidationError

from src.persona.agent import Stance
from src.simulation import agent_record
from src.simulation.agent_record import (
    AgentRecord,
    AgentView,
    CiteIds,
    GenerationInfo,
    NodeInfo,
    RankInfo,
    UniquenessInfo,
    ValidationInfo,
    dossier_hash,
)
from src.simulation.evidence import ChunkRow, RelationItem, build_pack


def _pack(text: str, relations: tuple[RelationItem, ...] = ()):
    chunk = ChunkRow("c1", "d1", "Pricing memo", "Market", text, 0.9)
    return build_pack("Lumen Pay", [], [chunk], list(relations))


def _relation(relation_type: str = "SUPPLIES") -> RelationItem:
    return RelationItem("r0", relation_type, "out", "n2", "Acme", "c1")


VIEW_FIELDS = {
    "name": "Lumen Pay",
    "type": "Competitor",
    "role": "Price challenger in the German SME market",
    "stance": Stance.NEGATIVE,
    "strength": 0.7,
    "bio": "Cuts prices in Berlin.",
    "details": "Claim one. Claim two.",
    "confidence": 0.62,
}


def _record(**overrides) -> AgentRecord:
    pack = _pack("Lumen Pay cuts prices in Berlin.")
    fields = dict(
        run_id="run-1",
        node_id="node-1",
        query_hash="qh",
        question="Should we enter Germany?",
        decision_axis="",
        node=NodeInfo(name="Lumen Pay", aliases=[], type_label="Competitor", type_source="graph"),
        rank=RankInfo(features={"query_relevance": 0.9}, score=0.8, seated=True, reason="", order=1),
        evidence=list(pack.items),
        relations=list(pack.relations),
        view=AgentView(**VIEW_FIELDS),
        details_raw="Claim one [e1]. Claim two.",
        cites=CiteIds(),
        validation=ValidationInfo(json_ok=True, repairs=0, rejected=[], details_chars=26, cites_valid=True),
        uniqueness=UniquenessInfo(),
        generation=GenerationInfo(model="m", prompt_version="p1", temperature=0.2, attempts=1, latency_ms=10),
        dossier_hash=dossier_hash(pack, "p1"),
        status="published",
    )
    return AgentRecord(**(fields | overrides))


def test_view_has_exactly_the_documented_keys():
    assert set(AgentView.model_fields) == {"name", "type", "role", "stance", "strength", "bio", "details", "confidence"}


def test_view_rejects_an_extra_field():
    with pytest.raises(ValidationError):
        AgentView(**VIEW_FIELDS, dossier_hash="leaked")


def test_record_rejects_an_unknown_status():
    with pytest.raises(ValidationError):
        _record(status="maybe")


def test_record_holds_the_real_evidence_items():
    assert _record().evidence[0].id == "e1"


@pytest.mark.parametrize("value", ["sort of", "", None])
def test_unknown_stance_raises_instead_of_becoming_neutral(value):
    with pytest.raises(ValueError):
        Stance.parse(value)


def test_stance_parse_trims_and_accepts_lowercase():
    assert Stance.parse("positive ") is Stance.POSITIVE


def test_stance_parse_accepts_abstain():
    assert Stance.parse("ABSTAIN") is Stance.ABSTAIN


def test_dossier_hash_changes_when_evidence_changes():
    pack_a = _pack("Lumen Pay cuts prices in Berlin.")
    pack_b = _pack("Lumen Pay raises prices in Berlin.")
    assert dossier_hash(pack_a, "p1") != dossier_hash(pack_b, "p1")


def test_dossier_hash_is_stable_across_calls():
    pack = _pack("Lumen Pay cuts prices in Berlin.", (_relation(),))
    assert dossier_hash(pack, "p1") == dossier_hash(pack, "p1")


def test_dossier_hash_changes_when_a_relation_changes():
    text = "Lumen Pay cuts prices in Berlin."
    assert dossier_hash(_pack(text, (_relation("SUPPLIES"),)), "p1") != dossier_hash(
        _pack(text, (_relation("OWNS"),)), "p1"
    )


def test_dossier_hash_changes_when_prompt_version_changes(monkeypatch):
    pack = _pack("Lumen Pay cuts prices in Berlin.")
    before = dossier_hash(pack, "p1")
    monkeypatch.setattr(agent_record, "PROFILE_PROMPT_VERSION", "p2")
    assert dossier_hash(pack, "p1") != before
