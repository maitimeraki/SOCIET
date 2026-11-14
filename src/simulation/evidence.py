"""Per-agent evidence: sentences that name the agent, plus its relations.

Spans are offsets inside the chunk text, computed here at query time, so no
graph change is needed. An item belongs to an agent only if its clipped text
(the first MAX_WORDS words of the sentence) names the agent or one of its
aliases, case-insensitively and on whole words. Ownership is by name match, not
entity identity: a sentence naming both "Amazon" and "Amazon Web Services" is
evidence for both agents, so overlapping names share sentences. Relations are
structured, not prose: a 1-hop neighbour is a relation counterpart, so there is
no separate neighbour origin. build_pack keeps the first MAX_RELATIONS relations
in caller order, so the caller must pre-sort them by its own ranking.
"""
import re
from dataclasses import dataclass

MAX_OWN, MAX_RELATIONS, MAX_WORDS = 12, 8, 40
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
_NEVER = re.compile(r"(?!)")


@dataclass(frozen=True)
class ChunkRow:
    chunk_id: str
    doc_id: str
    doc_title: str
    section: str
    text: str
    retrieval_score: float


@dataclass(frozen=True)
class EvidenceItem:
    id: str
    chunk_id: str
    doc_id: str
    doc_title: str
    section: str
    span: tuple[int, int]
    text: str
    origin: str
    retrieval_score: float


@dataclass(frozen=True)
class RelationItem:
    id: str
    type: str
    direction: str  # "out" | "in"
    counterpart_id: str
    counterpart_name: str
    chunk_id: str


@dataclass(frozen=True)
class EvidencePack:
    items: tuple[EvidenceItem, ...] = ()
    relations: tuple[RelationItem, ...] = ()
    doc_count: int = 0
    chunk_count: int = 0

    def ids(self) -> set[str]:
        return {i.id for i in self.items} | {r.id for r in self.relations}


def sentence_spans(text: str) -> list[tuple[int, int]]:
    spans, start = [], len(text) - len(text.lstrip())
    for m in _SENTENCE_BREAK.finditer(text):
        spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(text.rstrip())))
    return [(s, e) for s, e in spans if text[s:e].strip()]


def _clip(text: str, start: int, end: int) -> int:
    words = list(re.finditer(r"\S+", text[start:end]))
    return end if len(words) <= MAX_WORDS else start + words[MAX_WORDS - 1].end()


def _names_pattern(names: list[str]) -> re.Pattern[str]:
    # ponytail: a blank name list must match nothing, not everything (empty alternation matches "").
    alternatives = "|".join(re.escape(n) for n in sorted({n.strip() for n in names if n.strip()}, key=len, reverse=True))
    if not alternatives:
        return _NEVER
    return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE)


def build_pack(name: str, aliases: list[str], chunks: list[ChunkRow], relations: list[RelationItem]) -> EvidencePack:
    pattern = _names_pattern([name, *aliases])
    ranked = sorted(chunks, key=lambda c: (-c.retrieval_score, c.chunk_id))
    items: list[EvidenceItem] = []
    for chunk in ranked:
        for start, end in sentence_spans(chunk.text):
            end = _clip(chunk.text, start, end)
            if not pattern.search(chunk.text[start:end]):
                continue
            items.append(EvidenceItem(f"e{len(items) + 1}", chunk.chunk_id, chunk.doc_id, chunk.doc_title,
                                      chunk.section, (start, end), chunk.text[start:end], "own", chunk.retrieval_score))
            if len(items) == MAX_OWN:
                break
        if len(items) == MAX_OWN:
            break
    rels = tuple(RelationItem(f"r{i + 1}", r.type, r.direction, r.counterpart_id, r.counterpart_name, r.chunk_id)
                 for i, r in enumerate(relations[:MAX_RELATIONS]))
    return EvidencePack(tuple(items), rels, len({i.doc_id for i in items}), len({i.chunk_id for i in items}))
