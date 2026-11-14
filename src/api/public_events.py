"""The one boundary every run event and run result crosses toward a client or the log.

Default deny: an event type or key that is not listed here does not leave the
backend. Adding a key is a deliberate edit to this file plus its test.
"""
import logging
from collections.abc import Mapping
from typing import Any

logger = logging.getLogger(__name__)

_EVENT_KEYS: dict[str, frozenset[str]] = {
    "stage": frozenset({"type", "stage", "index", "query", "agents", "round", "pairs", "turns",
                        "converged", "rounds_executed", "share", "threshold"}),
    "intent": frozenset({"type", "intent"}),
    "selection": frozenset({"type", "rows"}),
    "agent": frozenset({"type", "profile", "index", "total"}),
    "pair_turn": frozenset({"type", "pair_id"}),
    "round": frozenset({"type", "round", "pairs", "turns", "consensus", "warnings"}),
    "commit": frozenset({"type", "round", "opinions", "edges", "failed", "error",
                         "written_nodes", "written_links"}),
    "activation": frozenset({"type", "round", "agents", "reasons"}),
    "complete": frozenset({"type", "converged", "verdict", "narrative", "narrative_status", "final_stances",
                           "warnings", "rounds_executed", "confidence_score", "weight_share", "contested",
                           "provenance_by_claim", "cluster_details", "supporting_entities",
                           "opposing_entities", "dissenting_views", "evidence"}),
    "error": frozenset({"type", "error", "warnings"}),
    "cancelled": frozenset({"type", "error"}),
    "ping": frozenset({"type"}),
    "ack": frozenset({"type", "data"}),
}
_INTENT_KEYS = frozenset({"core_question", "stance_axis", "direct_keywords", "latent_sectors",
                          "search_perspectives", "domain_tags", "entity_frame", "extraction_confidence"})
_ROW_KEYS = frozenset({"name", "semantic", "density", "blended"})
# Interim shape the existing roster UI reads; Track 3 narrows this to AgentView.
_PROFILE_KEYS = frozenset({"agent_id", "identity", "bio", "detailed_perspective", "role_description",
                           "stance", "intensity", "confidence", "conviction", "cior", "domain_tags",
                           "expertise_level", "discovery_type", "communication_radius"})
_RESULT_KEYS = frozenset({"converged", "verdict", "narrative", "narrative_status", "final_stances", "warnings",
                          "rounds_executed", "intent", "confidence_score", "weight_share", "contested",
                          "provenance_by_claim", "cluster_details", "supporting_entities",
                          "opposing_entities", "dissenting_views", "evidence"})


def _pick(source: Mapping[str, Any], keys: frozenset[str]) -> dict[str, Any]:
    return {k: v for k, v in source.items() if k in keys}


def project_event(event: Mapping[str, Any]) -> dict[str, Any] | None:
    kind = event.get("type")
    allowed = _EVENT_KEYS.get(kind)  # type: ignore[arg-type]
    if allowed is None:
        logger.warning("dropping unlisted run event type %r", kind)
        return None
    out = _pick(event, allowed)
    if kind == "intent":
        out["intent"] = _pick(event.get("intent") or {}, _INTENT_KEYS)
    elif kind == "selection":
        out["rows"] = [_pick(row, _ROW_KEYS) for row in event.get("rows") or []]
    elif kind == "agent":
        out["profile"] = _pick(event.get("profile") or {}, _PROFILE_KEYS)
    return out


def project_result(result: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if result is None:
        return None
    out = _pick(result, _RESULT_KEYS)
    if "intent" in out and isinstance(out["intent"], Mapping):
        out["intent"] = _pick(out["intent"], _INTENT_KEYS)
    claims = out.get("provenance_by_claim")
    if isinstance(claims, Mapping):
        out["provenance_by_claim"] = {
            claim: [{"title": l.get("title"), "breadcrumb": l.get("breadcrumb")} for l in links]
            for claim, links in claims.items()
        }
    return out
