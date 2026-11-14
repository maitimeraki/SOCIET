"""Seat ranking: features -> score -> eligibility -> MMR seating.

Pure and deterministic: the same candidates give the same decisions. The
weights are starting values; tune them on the golden set (tests/simulation/golden),
not by feel. No LLM call decides who is seated.
"""
import math
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

RRF_K = 60
PPR_ALPHA = 0.85
W_QUERY, W_ENTITY, W_PPR = 0.4, 0.2, 0.4
MMR_LAMBDA = 0.5
MIN_EVIDENCE = 2
_LEGAL_SUFFIXES = frozenset({"inc", "ltd", "llc", "gmbh", "corp", "co", "plc", "ag", "sa"})


class NoAgentsDerivableError(RuntimeError):
    """The graph holds no candidate that reaches this question: refuse, never invent a roster."""


def rrf_fuse(rankings: Sequence[Sequence[str]], k: int = RRF_K) -> dict[str, float]:
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            fused[key] = fused.get(key, 0.0) + 1.0 / (k + rank)
    return fused


def adjacency(edges: Iterable[tuple[str, str]]) -> dict[str, list[str]]:
    adj: dict[str, list[str]] = {}
    for a, b in edges:
        if a == b:
            continue
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    return adj


def personalized_pagerank(
    adj: Mapping[str, Sequence[str]],
    seeds: Mapping[str, float],
    alpha: float = PPR_ALPHA,
    iterations: int = 50,
) -> dict[str, float]:
    # Sorted everywhere: float sums must not depend on set/dict/input order (spec 7).
    nodes = sorted(set(adj) | {m for ns in adj.values() for m in ns} | set(seeds))
    if not nodes:
        return {}
    total = sum(seeds[s] for s in sorted(seeds))
    if total <= 0:
        return {n: 0.0 for n in nodes}
    restart = {n: seeds.get(n, 0.0) / total for n in nodes}
    neighbours = {n: sorted(adj.get(n, ())) for n in nodes}
    rank = dict(restart)
    for _ in range(iterations):
        nxt = {n: (1 - alpha) * restart[n] for n in nodes}
        dangling = 0.0
        for n in nodes:
            out = neighbours[n]
            if not out:
                dangling += rank[n]
                continue
            share = alpha * rank[n] / len(out)
            for m in out:
                nxt[m] += share
        for n in nodes:
            nxt[n] += alpha * dangling * restart[n]
        rank = nxt
    peak = max(rank.values())
    return {n: v / peak for n, v in rank.items()} if peak > 0 else rank


def percentile(value: float, population: Sequence[float]) -> float:
    """Share of population values <= value; 0.0 for an empty population."""
    return sum(1 for p in population if p <= value) / len(population) if population else 0.0


def cluster_key(name: str) -> str:
    text = unicodedata.normalize("NFKC", name).casefold()
    tokens = [t for t in re.split(r"[\W_]+", text) if t and not any(ch.isdigit() for ch in t)]
    tokens = [t for t in tokens if t not in _LEGAL_SUFFIXES]
    return " ".join(tokens) or text.strip()


@dataclass(frozen=True)
class Candidate:
    entity_id: str
    name: str
    type_label: str = ""
    query_relevance: float = 0.0
    entity_similarity: float = 0.0
    ppr: float = 0.0
    doc_count: int = 0
    chunk_count: int = 0
    evidence_count: int = 0
    is_actor: bool = True
    vector: tuple[float, ...] = ()


def _grounding(c: Candidate) -> float:
    docs = min(1.0, math.log(1 + c.doc_count) / math.log(6))
    chunks = min(1.0, c.chunk_count / 4)
    return (docs + chunks) / 2  # decision 16: arithmetic mean


def score(c: Candidate) -> float:
    core = W_QUERY * c.query_relevance + W_ENTITY * c.entity_similarity + W_PPR * c.ppr
    return core * (0.5 + 0.5 * _grounding(c))


def features(c: Candidate) -> dict[str, float]:
    return {
        "query_relevance": c.query_relevance,
        "entity_similarity": c.entity_similarity,
        "ppr": c.ppr,
        "grounding": _grounding(c),
        "evidence_count": float(c.evidence_count),
    }


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return max(0.0, sum(x * y for x, y in zip(a, b)) / (na * nb)) if na and nb else 0.0


@dataclass
class SeatDecision:
    entity_id: str
    name: str
    score: float
    features: dict[str, float] = field(default_factory=dict)
    seated: bool = False
    reason: str = ""
    order: int | None = None


class SeatQueue:
    """Eligibility, then Maximal Marginal Relevance. A rejected profile frees its
    seat for the next eligible candidate; nothing is re-scored.

    One draw at a time: next() refuses while a draw is unresolved, so accepts never
    exceed n. Task 1.5 callers must dedupe by entity_id before building the queue."""

    def __init__(self, candidates: Iterable[Candidate], n: int):
        self._n = n
        self._seated: list[Candidate] = []
        self._pool: list[Candidate] = []
        self._drawn: dict[str, Candidate] = {}
        self._decisions: dict[str, SeatDecision] = {}
        ordered = sorted(candidates, key=lambda c: (-score(c), c.name, c.entity_id))
        ids = [c.entity_id for c in ordered]
        if len(set(ids)) != len(ids):
            raise ValueError(f"duplicate entity_id in candidates: {sorted({i for i in ids if ids.count(i) > 1})}")
        seen: set[str] = set()
        for c in ordered:
            reason = ""
            if not c.is_actor:
                reason = "not an actor"
            elif c.evidence_count < MIN_EVIDENCE:
                reason = f"evidence {c.evidence_count} < {MIN_EVIDENCE}"
            elif cluster_key(c.name) in seen:
                reason = "duplicate of a higher-ranked cluster member"
            else:
                seen.add(cluster_key(c.name))
                self._pool.append(c)
                reason = "eligible, not reached"
            self._decisions[c.entity_id] = SeatDecision(c.entity_id, c.name, score(c), features(c), reason=reason)

    def _penalty(self, c: Candidate) -> float:
        return max((cosine(c.vector, s.vector) for s in self._seated), default=0.0)

    def _require_drawn(self, c: Candidate) -> None:
        if not isinstance(c, Candidate):
            raise ValueError(f"expected a Candidate, got {c!r}")
        drawn = self._drawn.get(c.entity_id)
        if drawn is None:
            raise ValueError(f"{c.name} was not drawn by next() or is already resolved")
        if drawn is not c:
            raise ValueError(f"{c.name} is not the object next() drew")

    def next(self) -> Candidate | None:
        if self._drawn:
            raise ValueError("a draw is unresolved: accept or reject it before drawing again")
        if len(self._seated) >= self._n or not self._pool:
            return None
        best = min(self._pool, key=lambda c: (-(score(c) - MMR_LAMBDA * self._penalty(c)), c.name, c.entity_id))
        self._pool.remove(best)
        self._drawn[best.entity_id] = best
        self._decisions[best.entity_id].reason = "drawn, unresolved"
        return best

    def accept(self, c: Candidate) -> None:
        self._require_drawn(c)
        del self._drawn[c.entity_id]
        self._seated.append(c)
        d = self._decisions[c.entity_id]
        d.seated, d.reason, d.order = True, "seated", len(self._seated)

    def reject(self, c: Candidate, reason: str) -> None:
        self._require_drawn(c)
        del self._drawn[c.entity_id]
        self._decisions[c.entity_id].reason = f"rejected: {reason}"

    def decisions(self) -> list[SeatDecision]:
        return sorted(self._decisions.values(), key=lambda d: (d.order is None, d.order or 0, -d.score, d.name))
