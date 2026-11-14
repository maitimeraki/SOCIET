from dataclasses import replace

from src.simulation.evidence import EvidenceItem, EvidencePack, RelationItem
from src.simulation.profile_validation import (
    BIO_SIM_MAX,
    DETAILS_SIM_MAX,
    ProfileDraft,
    check_uniqueness,
    strip_markers,
    validate_profile,
)

PACK = EvidencePack(
    items=(EvidenceItem("e1", "c1", "d1", "Memo", "", (0, 30), "Lumen Pay is cutting margin pricing in Berlin", "own", 1.0),
           EvidenceItem("e2", "c2", "d2", "Note", "", (0, 30), "German banks signed on to the Lumen platform", "own", 0.9)),
    relations=(RelationItem("r1", "COMPETES_WITH", "out", "x", "Kestra", "c1"),),
    doc_count=2, chunk_count=2)
DETAILS = " ".join(f"Point {i} rests on the pricing argument [e{1 + i % 2}]." for i in range(40))


def draft(**over):
    base = dict(role="Argues the entry meets a discount", stance="negative", strength=0.7,
                bio="Lumen pays attention to pricing pressure across Berlin and the wider German market, and expects "
                    "a discount from the first quarter of any 2027 entry into that market.",
                details=DETAILS, confidence=0.4,
                cites={"role": ["e1"], "stance": ["e1"], "bio": ["e2"], "confidence": []})
    return {**base, **over}

def reasons(raw): return {r.field for r in validate_profile(raw, PACK)[1]}
def test_a_good_draft_passes():                      assert validate_profile(draft(), PACK)[1] == []
def test_unknown_cite_id_is_rejected():              assert "cites" in reasons(draft(cites={"role": ["e9"], "stance": ["e1"], "bio": ["e2"], "confidence": []}))
def test_abstain_must_have_no_stance_cites():        assert "stance" in reasons(draft(stance="abstain"))
def test_non_abstain_needs_a_stance_cite():          assert "stance" in reasons(draft(cites={"role": ["e1"], "stance": [], "bio": ["e2"], "confidence": []}))
def test_short_details_are_repairable():
    rejection = next(r for r in validate_profile(draft(details="Too short [e1] [e2]."), PACK)[1] if r.field == "details")
    assert rejection.repairable
def test_details_need_two_valid_markers():           assert "details" in reasons(draft(details=DETAILS.replace("[e2]", "[e1]")))
def test_marker_to_unknown_id_is_rejected():         assert "details" in reasons(draft(details=DETAILS + " Extra [e7]."))
def test_bio_must_use_a_term_from_the_pack():        assert "bio" in reasons(draft(bio="Something entirely unrelated to anything supplied " * 3))
def test_bio_without_pack_term_is_rejected_at_valid_length():
    assert "bio" in reasons(draft(bio="Something entirely unrelated to anything supplied " * 4))
def test_verbatim_copy_is_evidence_dumping():
    long_text = " ".join(f"word{i}" for i in range(30))              # a 30-word evidence sentence
    pack = EvidencePack(items=(replace(PACK.items[0], text=long_text),) + PACK.items[1:],
                        relations=PACK.relations, doc_count=2, chunk_count=2)
    copied = f"{long_text} [e1] [e2] " + DETAILS
    details_rejections = [r for r in validate_profile(draft(details=copied), pack)[1] if r.field == "details"]
    assert any("copied" in r.reason for r in details_rejections)
def test_confidence_above_half_with_one_document_is_repairable():
    one_doc = EvidencePack(PACK.items, PACK.relations, doc_count=1, chunk_count=2)
    rejection = next(r for r in validate_profile(draft(confidence=0.8), one_doc)[1] if r.field == "confidence")
    assert rejection.repairable
def test_markers_are_stripped_from_the_view():        assert "[e1]" not in strip_markers(DETAILS)

def test_identical_details_fail_the_8gram_check():
    a, b = ProfileDraft(**draft()), ProfileDraft(**draft())
    report = check_uniqueness({"A": a, "B": b}, {"A": (1.0, 0.0), "B": (0.0, 1.0)})
    assert report.max_details_sim > DETAILS_SIM_MAX and ("A", "B") in report.failing_pairs

def test_similar_bios_fail_the_cosine_check():
    a, b = ProfileDraft(**draft()), ProfileDraft(**draft(details=DETAILS.replace("pricing", "regulatory")))
    report = check_uniqueness({"A": a, "B": b}, {"A": (1.0, 0.0), "B": (1.0, 0.01)})
    assert report.max_bio_sim > BIO_SIM_MAX and ("A", "B") in report.failing_pairs
