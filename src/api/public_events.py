"""The one boundary every run event and run result crosses toward a client or the log.

Default deny: an event type or key that is not listed here does not leave the
backend. Adding a key is a deliberate edit to this file plus its test.
"""
import logging
from collections.abc import Mapping
from typing import Any

logger = logging.getLogger(__name__)

_INTENT_KEYS = frozenset({"core_question", "stance_axis", "direct_keywords", "latent_sectors",
                          "search_perspectives", "domain_tags", "entity_frame", "extraction_confidence"})
# interim: selection scores are shown by the roster today; Task 1.5 drops the
# scores from the wire and Task 3.2 removes `selection` altogether.
_ROW_KEYS = frozenset({"name", "semantic", "density", "blended"})
# interim: the roster UI reads these profile extras; Task 2.x narrows the
# profile to the ranked seat and Task 3.1 switches the frontend to AgentView.
_PROFILE_KEYS = frozenset({"agent_id", "identity", "bio", "detailed_perspective", "role_description",
                           "stance", "intensity", "confidence", "conviction", "cior", "domain_tags",
                           "expertise_level", "discovery_type", "communication_radius"})
# The verdict keys a client may see, shared by the `complete` event and the
# stored or served result. One list: a key added here reaches both.
_VERDICT_KEYS = frozenset({"converged", "verdict", "narrative", "narrative_status", "final_stances", "warnings",
                           "rounds_executed", "confidence_score", "weight_share", "contested",
                           "provenance_by_claim", "cluster_details", "supporting_entities",
                           "opposing_entities", "dissenting_views", "evidence"})
_COMPLETE_KEYS = _VERDICT_KEYS | {"type"}
_RESULT_KEYS = _VERDICT_KEYS | {"intent"}
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
    "complete": _COMPLETE_KEYS,
    "error": frozenset({"type", "error", "warnings"}),
    "cancelled": frozenset({"type", "error"}),
    "ping": frozenset({"type"}),
    "ack": frozenset({"type", "data"}),
}


def _pick(source: Any, keys: frozenset[str]) -> dict[str, Any]:
    # Fail closed: anything that is not a mapping carries no keys at all.
    if not isinstance(source, Mapping):
        return {}
    return {k: v for k, v in source.items() if k in keys}


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _narrow_provenance(claims: Any) -> dict[str, list[dict[str, Any]]]:
    # Titles and breadcrumbs only: no document id, chunk id, span or quote.
    if not isinstance(claims, Mapping):
        return {}
    return {
        claim: [
            {"title": _text(link.get("title")), "breadcrumb": _text(link.get("breadcrumb"))}
            for link in (links if isinstance(links, (list, tuple)) else [])
            if isinstance(link, Mapping)
        ]
        for claim, links in claims.items()
    }


def _narrow_verdict(source: Mapping[str, Any], keys: frozenset[str]) -> dict[str, Any]:
    out = _pick(source, keys)
    if "intent" in out:
        out["intent"] = _pick(out["intent"], _INTENT_KEYS)
    if "provenance_by_claim" in out:
        out["provenance_by_claim"] = _narrow_provenance(out["provenance_by_claim"])
    return out


def project_event(event: Mapping[str, Any]) -> dict[str, Any] | None:
    kind = event.get("type")
    if not isinstance(kind, str):
        # Logged by type only: the payload may be what must not leave.
        logger.warning("dropping run event with a non-string type (%s)", type(kind).__name__)
        return None
    allowed = _EVENT_KEYS.get(kind)
    if allowed is None:
        logger.warning("dropping unlisted run event type %r", kind)
        return None
    if kind == "complete":
        return _narrow_verdict(event, allowed)
    out = _pick(event, allowed)
    if kind == "intent":
        out["intent"] = _pick(event.get("intent"), _INTENT_KEYS)
    elif kind == "selection":
        rows = event.get("rows")
        out["rows"] = [_pick(row, _ROW_KEYS) for row in rows] if isinstance(rows, list) else []
    elif kind == "agent":
        out["profile"] = _pick(event.get("profile"), _PROFILE_KEYS)
    return out


def project_result(result: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if result is None:
        return None
    return _narrow_verdict(result, _RESULT_KEYS)
