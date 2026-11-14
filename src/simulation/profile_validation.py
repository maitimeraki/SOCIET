"""Code-side checks on one agent profile, and roster-level uniqueness. Pure: no LLM, no I/O.

Spec 3d (per profile) and 3e (across the roster). A repairable rejection is one where a
single repair call may fix the draft; the caller decides whether to make that call.
"""
from __future__ import annotations

import itertools
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from src.simulation.evidence import EvidencePack
from src.simulation.ranking import cosine

DETAILS_MIN, DETAILS_MAX = 1500, 2100
BIO_SIM_MAX, DETAILS_SIM_MAX = 0.85, 0.10
BIO_WORDS_MIN, BIO_WORDS_MAX = 25, 60
COPY_RUN_WORDS = 25
SHINGLE_WORDS = 8
SINGLE_DOC_CONFIDENCE_MAX = 0.5
TERM_MIN_LEN = 5

CITE_MARKER = re.compile(r"\[([^\[\]]+)\]")
_MARKER_WITH_SPACE = re.compile(r"\s*\[[^\[\]]+\]")
_SENTENCE_END = re.compile(r"[.!?](?:\s*\[[^\[\]]+\])*(?=\s|$)")
_WORD = re.compile(r"\w+")


class ProfileDraft(BaseModel):
    role: str
    stance: Literal["positive", "negative", "neutral", "abstain"]
    strength: float = Field(ge=0, le=1)
    bio: str
    details: str
    confidence: float = Field(ge=0, le=1)
    cites: dict[str, list[str]]


# Internal diagnostics only (spec 4b): reasons and similarity numbers must never be
# forwarded to a client, the WebSocket, run_events or runs.verdict.
@dataclass(frozen=True)
class Rejection:
    field: str
    reason: str
    repairable: bool


# Internal diagnostics only (spec 4b): similarity numbers and failing pairs must never be
# forwarded to a client, the WebSocket, run_events or runs.verdict.
@dataclass(frozen=True)
class UniquenessReport:
    max_bio_sim: float
    max_details_sim: float
    max_cite_overlap: float
    failing_pairs: list[tuple[str, str]]


def strip_markers(text: str) -> str:
    return _MARKER_WITH_SPACE.sub("", text).strip()


def split_sentences(text: str) -> list[str]:
    """Sentences of a details text. A cite marker written right after a sentence's end stays with it."""
    pieces, start = [], 0
    for match in _SENTENCE_END.finditer(text):
        pieces.append(text[start:match.end()].strip())
        start = match.end()
    pieces.append(text[start:].strip())
    return [piece for piece in pieces if piece]


def has_valid_marker(sentence: str, valid_ids: set[str]) -> bool:
    return any(marker in valid_ids for marker in CITE_MARKER.findall(sentence))


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _ngrams(text: str, n: int) -> set[tuple[str, ...]]:
    words = _words(text)
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def _evidence_runs(pack: EvidencePack) -> set[tuple[str, ...]]:
    return set().union(*(_ngrams(item.text, COPY_RUN_WORDS) for item in pack.items))


def _pack_terms(pack: EvidencePack) -> set[str]:
    texts = [item.text for item in pack.items] + [r.counterpart_name for r in pack.relations]
    return {w for text in texts for w in _words(text) if len(w) >= TERM_MIN_LEN}


def _drop_unknown_cites(draft: ProfileDraft, pack: EvidencePack) -> ProfileDraft:
    known = pack.ids()
    cites = {field: [cid for cid in ids if cid in known] for field, ids in draft.cites.items()}
    return draft.model_copy(update={"cites": cites})


def _check_role(draft: ProfileDraft, pack: EvidencePack) -> Rejection | None:
    if not draft.cites.get("role"):
        return Rejection("role", "role needs at least one valid cite", False)
    return None


def _check_stance(draft: ProfileDraft, pack: EvidencePack) -> Rejection | None:
    cited = draft.cites.get("stance", [])
    if draft.stance == "abstain":
        return Rejection("stance", "abstain must not cite evidence", False) if cited else None
    if not cited:
        return Rejection("stance", "non-abstain stance needs at least one valid cite", False)
    return None


def _check_cites(draft: ProfileDraft, pack: EvidencePack) -> Rejection | None:
    required = ["role", "bio"] + ([] if draft.stance == "abstain" else ["stance"])
    missing = [field for field in required if not draft.cites.get(field)]
    if missing:
        return Rejection("cites", f"no valid cite for {', '.join(missing)}", False)
    return None


def _check_bio(draft: ProfileDraft, pack: EvidencePack) -> Rejection | None:
    words = _words(draft.bio)
    if not BIO_WORDS_MIN <= len(words) <= BIO_WORDS_MAX:
        return Rejection("bio", f"bio has {len(words)} words, need {BIO_WORDS_MIN}-{BIO_WORDS_MAX}", False)
    own_ids = {item.id for item in pack.items if item.origin == "own"}
    if not own_ids & set(draft.cites.get("bio", [])):
        return Rejection("bio", "bio must cite at least one own item", False)
    if not set(words) & _pack_terms(pack):
        return Rejection("bio", "bio uses no term from the evidence", False)
    return None


def _check_details_length(draft: ProfileDraft, pack: EvidencePack) -> Rejection | None:
    n = len(draft.details)
    if DETAILS_MIN <= n <= DETAILS_MAX:
        return None
    return Rejection("details", f"details is {n} characters, need {DETAILS_MIN}-{DETAILS_MAX}", True)


def _check_details_markers(draft: ProfileDraft, pack: EvidencePack) -> Rejection | None:
    markers = CITE_MARKER.findall(draft.details)
    valid = pack.ids()
    if any(marker not in valid for marker in markers):
        return Rejection("details", "details has a cite marker that is not in the pack", False)
    if len(set(markers)) < 2:
        return Rejection("details", "details needs at least two distinct cite markers", False)
    return None


def _check_sentence_markers(draft: ProfileDraft, pack: EvidencePack) -> Rejection | None:
    valid = pack.ids()
    if all(has_valid_marker(sentence, valid) for sentence in split_sentences(draft.details)):
        return None
    return Rejection("details", "a sentence in details has no valid cite marker", True)


def _check_copying(draft: ProfileDraft, pack: EvidencePack) -> Rejection | None:
    if _ngrams(strip_markers(draft.details), COPY_RUN_WORDS) & _evidence_runs(pack):
        return Rejection("details", f"details has {COPY_RUN_WORDS}+ consecutive words copied from the evidence", False)
    return None


def _check_confidence(draft: ProfileDraft, pack: EvidencePack) -> Rejection | None:
    if draft.confidence > SINGLE_DOC_CONFIDENCE_MAX and pack.doc_count == 1:
        return Rejection("confidence", f"confidence {draft.confidence} needs more than one document, found 1", True)
    return None


_CHECKS: tuple[Callable[[ProfileDraft, EvidencePack], Rejection | None], ...] = (
    _check_role,
    _check_stance,
    _check_cites,
    _check_bio,
    _check_details_length,
    _check_details_markers,
    _check_sentence_markers,
    _check_copying,
    _check_confidence,
)


def validate_profile(raw: Mapping, pack: EvidencePack) -> tuple[ProfileDraft | None, list[Rejection]]:
    try:
        draft = ProfileDraft.model_validate(raw)
    except ValidationError as exc:
        reason = "; ".join(f"{'.'.join(map(str, e['loc']))} {e['msg']}" for e in exc.errors())
        return None, [Rejection("json", reason, True)]
    draft = _drop_unknown_cites(draft, pack)
    rejections = [r for check in _CHECKS if (r := check(draft, pack)) is not None]
    return (None if rejections else draft), rejections


def _jaccard(a: set, b: set) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def check_uniqueness(drafts: Mapping[str, ProfileDraft], bio_vectors: Mapping[str, Sequence[float]]) -> UniquenessReport:
    names = sorted(drafts)
    shingles = {n: _ngrams(strip_markers(drafts[n].details), SHINGLE_WORDS) for n in names}
    cited = {n: {cid for ids in drafts[n].cites.values() for cid in ids} for n in names}
    bio_sims, details_sims, cite_overlaps, failing = [], [], [], []
    for a, b in itertools.combinations(names, 2):
        bio = cosine(bio_vectors[a], bio_vectors[b])
        details = _jaccard(shingles[a], shingles[b])
        bio_sims.append(bio)
        details_sims.append(details)
        cite_overlaps.append(_jaccard(cited[a], cited[b]))
        if bio > BIO_SIM_MAX or details > DETAILS_SIM_MAX:
            failing.append((a, b))
    return UniquenessReport(max(bio_sims, default=0.0), max(details_sims, default=0.0),
                            max(cite_overlaps, default=0.0), failing)
