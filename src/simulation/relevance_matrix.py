"""S4 — the Relevance-Knowledge Matrix: intent-consuming candidate selection.

Selection used to be density-only (structural relevance sums). S4 makes it read
the S3 query intent as well, and makes every row explainable: `semantic` (the
share of the intent's keyword/entity frame and domain/capability tags the
candidate's text covers), `density` (its structural relevance evidence, scaled
to [0, 1] across the batch) and `blended` (`w1*semantic + w2*density`, weights
from `DebateConfig`).

Both selection surfaces route through `rank_candidates` so the score exists once:
  * the debate path — `ProfileSynthesizer.synthesize`
  * `/hatch`        — `PersonaRepository.find_agent_sectors`

`density_component` is the single density entry point for both: P2-B replaces
that one body with the graph-model adapter (S4 design rule — the Phase 4 graph
change touches one location).
"""
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from src.simulation.debate_config import DebateConfig

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_MIN_TERM_LENGTH = 2


class NoAgentsDerivableError(RuntimeError):
    """The graph holds no candidate for this query, so no agent is derivable.

    The agents-from-graph-only invariant: selection never invents a roster, so
    the job fails loudly instead of debating with nobody.
    """


@dataclass(frozen=True)
class SelectionCandidate:
    """One rankable candidate: its identity, the text scored against the intent,
    and the raw graph evidence behind its density component."""

    name: str
    text: str
    evidence: Sequence[Any]


@dataclass(frozen=True)
class SelectionRow:
    """One ranked S4 row, explainable field by field.

    `semantic` and `density` are the two components of `blended`
    (`w1*semantic + w2*density`); `density` is normalized to [0, 1] across the
    batch so the decomposition adds up as documented. P2-B adds the provenance
    anchor field here.
    """

    name: str
    semantic: float
    density: float
    blended: float


def density_component(evidence: Sequence[Any]) -> float:
    """Raw density/structural component of a candidate — sum of its relevance evidence.

    THE density entry point for S4: each surface hands in its own graph rows
    (entity nodes for the debate path, sector rows for `/hatch`) and reads the
    sum back, so P2-B's graph-model adapter replaces this one body.
    """
    total = 0.0
    for item in evidence or ():
        if isinstance(item, Mapping):
            raw = item.get("total_relevance", item.get("relevance_score", 0.0))
        else:
            raw = getattr(item, "relevance_score", 0.0)
        try:
            total += float(raw or 0.0)
        except (TypeError, ValueError):
            continue
    return total


def intent_terms(intent: Any) -> list[str]:
    """The intent's keyword/entity frame plus its domain/capability tags.

    Accepts a `QueryIntent` or its mapping form (the `/hatch` path passes the
    `llm_output` dict when no intent object is available).
    """
    terms: list[str] = []
    for field in ("direct_keywords", "entity_frame", "domain_tags"):
        values = intent.get(field) if isinstance(intent, Mapping) else getattr(intent, field, None)
        terms.extend(str(value) for value in (values or []) if str(value).strip())
    return terms


def semantic_component(terms: Sequence[str], text: str) -> float:
    """Share of the intent `terms` that `text` covers, in [0, 1].

    A term matches when it appears verbatim (case-insensitive, word-bounded) or
    when every one of its tokens appears in the text. Terms shorter than two
    characters are ignored. No terms (or no text) scores 0.0 — a degraded intent
    ranks by density alone.
    """
    haystack = (text or "").lower()
    if not haystack:
        return 0.0
    tokens = set(_TOKEN_RE.findall(haystack))
    counted = matched = 0
    for term in terms:
        needle = str(term).strip().lower()
        if len(needle) < _MIN_TERM_LENGTH:
            continue
        counted += 1
        term_tokens = set(_TOKEN_RE.findall(needle))
        if re.search(rf"\b{re.escape(needle)}\b", haystack) or (term_tokens and term_tokens <= tokens):
            matched += 1
    return matched / counted if counted else 0.0


def blended_score(semantic: float, density: float, config: DebateConfig) -> float:
    """The documented blend: `w1*semantic + w2*density` (both components in [0, 1])."""
    return config.w1 * semantic + config.w2 * density


def rank_candidates(
    candidates: Sequence[SelectionCandidate],
    intent: Any,
    config: DebateConfig,
) -> list[SelectionRow]:
    """Score, blend and order candidates best-first.

    Ordering is the blended score when the intent ranks at least one candidate
    above `config.selection_score_threshold`. When no candidate clears it, the
    previous density-only ordering is restored and a warning says so. With no
    intent terms at all there is nothing to clear: density-only ordering, no
    warning — the pre-S4 behaviour for callers that pass no intent.
    """
    candidates = list(candidates)
    raw_density = [density_component(candidate.evidence) for candidate in candidates]
    peak = max(raw_density, default=0.0)
    terms = intent_terms(intent) if intent is not None else []

    rows: list[SelectionRow] = []
    for candidate, raw in zip(candidates, raw_density):
        semantic = semantic_component(terms, candidate.text)
        density = raw / peak if peak > 0 else 0.0
        rows.append(SelectionRow(
            name=candidate.name,
            semantic=semantic,
            density=density,
            blended=blended_score(semantic, density, config),
        ))

    if terms and any(row.blended >= config.selection_score_threshold for row in rows):
        rows.sort(key=lambda row: row.blended, reverse=True)
        return rows

    if terms:
        logger.warning(
            "S4 selection: no candidate cleared selection_score_threshold=%.2f "
            "(best blended=%.3f) — falling back to density-only ordering.",
            config.selection_score_threshold,
            max((row.blended for row in rows), default=0.0),
        )
    rows.sort(key=lambda row: row.density, reverse=True)
    return rows
