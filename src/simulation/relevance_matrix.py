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

`density_component` is the single density entry point for both, and its whole
shape read lives in `_evidence_row` — the graph-row adapter (S4 design rule:
the Phase 4 graph change touches that one body, and nothing else reads evidence
rows). Selected rows also carry the provenance `anchors` of their evidence,
read through the same adapter.
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
    batch so the decomposition adds up as documented. `anchors` are the
    provenance anchors of the candidate's evidence — source node ids/names and
    chunk ids where the row carries them, deduped and in evidence order — the
    stable join key Phase 3 and Phase 4 use to link a row back to the graph.
    """

    name: str
    semantic: float
    density: float
    blended: float
    anchors: tuple[dict[str, str], ...] = ()


def density_component(evidence: Sequence[Any]) -> float:
    """Raw density/structural component of a candidate — sum of its relevance evidence.

    THE density entry point for S4: each surface hands in its own graph rows
    (entity nodes for the debate path, sector rows for `/hatch`) and reads the
    sum back. The one shape read is `_evidence_row` — P4-T1 updates that body.
    """
    return sum(_evidence_row(item)[0] for item in evidence or ())


def _evidence_row(item: Any) -> tuple[float, tuple[dict[str, str], ...]]:
    """THE graph-row adapter — the single place that reads an evidence row.

    Returns `(raw_density, anchors)` for either surface's row shape:
      * a mapping (a `/hatch` sector row): density from `total_relevance`
        (falling back to `relevance_score`); anchors are the persona names in
        `evidence_nodes` — Persona nodes are identified by name, no id exists.
      * an object (a debate-path `EntityNode`): density from `.relevance_score`;
        anchors from `.id` / `.name` plus any `chunk_id` / `chunk_ids` its
        `.properties` carries. Ids are only ever carried, never invented.

    P4-T1 replaces this one body for the Document-first graph model; density
    and anchors on both surfaces are read through here and nowhere else.
    """
    if isinstance(item, Mapping):
        raw = item.get("total_relevance", item.get("relevance_score", 0.0))
        anchors = tuple(
            {"kind": "node", "name": str(name)}
            for name in (item.get("evidence_nodes") or [])
            if str(name or "").strip()
        )
    else:
        raw = getattr(item, "relevance_score", 0.0)
        node: dict[str, str] = {"kind": "node"}
        for key in ("id", "name"):
            value = str(getattr(item, key, "") or "").strip()
            if value:
                node[key] = value
        anchors = (node,) if len(node) > 1 else ()
        properties = getattr(item, "properties", None)
        if isinstance(properties, Mapping):
            chunk_refs = [properties.get("chunk_id")]
            chunk_ids = properties.get("chunk_ids")
            if isinstance(chunk_ids, (list, tuple, set)):
                chunk_refs.extend(chunk_ids)
            anchors += tuple(
                {"kind": "chunk", "id": str(ref)}
                for ref in chunk_refs
                if str(ref or "").strip()
            )
    try:
        density = float(raw or 0.0)
    except (TypeError, ValueError):
        density = 0.0
    return density, anchors


def _anchors_of(evidence: Sequence[Any]) -> tuple[dict[str, str], ...]:
    """The provenance anchors of one candidate's evidence: source node ids and
    names (and chunk ids where the row carries them), deduped, evidence order
    kept."""
    seen: set[tuple[str | None, str | None, str | None]] = set()
    anchors: list[dict[str, str]] = []
    for item in evidence or ():
        for anchor in _evidence_row(item)[1]:
            key = (anchor.get("kind"), anchor.get("id"), anchor.get("name"))
            if key not in seen:
                seen.add(key)
                anchors.append(anchor)
    return tuple(anchors)


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
    warnings: list[str] | None = None,
) -> list[SelectionRow]:
    """Score, blend and order candidates best-first.

    Ordering is the blended score when the intent ranks at least one candidate
    above `config.selection_score_threshold`. When no candidate clears it, the
    previous density-only ordering is restored and a warning says so. With no
    intent terms at all there is nothing to clear: density-only ordering, no
    warning — the pre-S4 behaviour for callers that pass no intent.

    `warnings` is an optional caller-owned list the fallback message is also
    appended to, so the degradation reaches the run result (S9) and not only
    the log stream. Every row carries the provenance `anchors` of its
    candidate's evidence. Pure function otherwise; nothing is mutated but
    that list.
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
            anchors=_anchors_of(candidate.evidence),
        ))

    if terms and any(row.blended >= config.selection_score_threshold for row in rows):
        rows.sort(key=lambda row: row.blended, reverse=True)
        return rows

    if terms:
        message = (
            "S4 selection: no candidate cleared selection_score_threshold="
            f"{config.selection_score_threshold:.2f} "
            f"(best blended={max((row.blended for row in rows), default=0.0):.3f})"
            " — falling back to density-only ordering."
        )
        logger.warning("%s", message)
        if warnings is not None:
            warnings.append(message)
    rows.sort(key=lambda row: row.density, reverse=True)
    return rows
