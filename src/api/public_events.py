"""The one boundary every run event and run result crosses toward a client or the log.

Default deny: an event type or key that is not listed here does not leave the
backend. Adding a key is a deliberate edit to this file plus its test.
"""
import logging
from collections.abc import Mapping
from typing import Any

from src.utils.labels import label_text, public_source

logger = logging.getLogger(__name__)

# What a client sees when a run or job fails for a reason we did not author.
# The exception text stays in the server log.
RUN_FAILED_MESSAGE = "The run failed. Try again, or contact support with the run id."
# What a verdict retry's job says when the report still fails its checks. The run stays not_produced;
# the checks and the model's text stay in the server log.
REPORT_NOT_PRODUCED_MESSAGE = (
    "The report could not be produced. The run is unchanged; you can retry again."
)
# What the owner sees when metering stops a run: the accounting state, authored here, never the raw reason.
METERING_STOPPED_MESSAGE = (
    "This run stopped: the usage limit for this period was reached, or usage could not be recorded. "
    "Check your usage, then try again."
)

_INTENT_KEYS = frozenset({"core_question", "stance_axis", "direct_keywords", "latent_sectors",
                          "search_perspectives", "domain_tags", "entity_frame", "extraction_confidence"})
# The profile a client sees is AgentView (spec 4a) and nothing else.
_PROFILE_KEYS = frozenset({"name", "type", "role", "stance", "strength", "bio", "details", "confidence"})
# The verdict keys a client may see, shared by the `complete` event and the
# served result. One list: a key added here reaches both. `sources` is the
# report's public source map, narrowed to {document, section} in _narrow_sources.
# `source_refs`, `attempts` and `checks` are backend-only: never in this list.
_VERDICT_KEYS = frozenset({"converged", "final_stances", "warnings", "rounds_executed", "confidence_score",
                           "weight_share", "contested", "provenance_by_claim", "cluster_details",
                           "supporting_entities", "opposing_entities",
                           "title", "markdown", "position", "sources", "status"})
# Stored with the result but never served: the report's source refs, its attempts and its checks,
# and the inputs a verdict retry rebuilds the report from (context, per-turn cites and strength).
_BACKEND_RESULT_KEYS = frozenset({"source_refs", "attempts", "checks", "retry_inputs"})
_COMPLETE_KEYS = _VERDICT_KEYS | {"type"}
_RESULT_KEYS = _VERDICT_KEYS | {"intent"}
_EVENT_KEYS: dict[str, frozenset[str]] = {
    "stage": frozenset({"type", "stage", "index", "query", "agents", "round", "pairs", "turns",
                        "converged", "rounds_executed", "share", "threshold"}),
    "intent": frozenset({"type", "intent"}),
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


def _narrow_provenance(claims: Any) -> dict[str, list[dict[str, Any]]]:
    # Titles and breadcrumbs only: no document id, chunk id, span or quote.
    if not isinstance(claims, Mapping):
        return {}
    return {
        claim: [
            {"title": label_text(link.get("title")), "breadcrumb": label_text(link.get("breadcrumb"))}
            for link in (links if isinstance(links, (list, tuple)) else [])
            if isinstance(link, Mapping)
        ]
        for claim, links in claims.items()
    }


def _narrow_sources(sources: Any) -> dict[str, dict[str, str]]:
    if not isinstance(sources, Mapping):
        return {}
    narrowed: dict[str, dict[str, str]] = {}
    for number, source in sources.items():
        public = public_source(source)
        if public is not None:
            narrowed[str(number)] = public
    return narrowed


def _narrow_verdict(source: Mapping[str, Any], keys: frozenset[str]) -> dict[str, Any]:
    out = _pick(source, keys)
    if "intent" in out:
        out["intent"] = _pick(out["intent"], _INTENT_KEYS)
    if "provenance_by_claim" in out:
        out["provenance_by_claim"] = _narrow_provenance(out["provenance_by_claim"])
    if "sources" in out:
        out["sources"] = _narrow_sources(out["sources"])
    return out


def project_event(event: Mapping[str, Any]) -> dict[str, Any] | None:
    if not isinstance(event, Mapping):
        logger.warning("dropping run event that is not a mapping (%s)", type(event).__name__)
        return None
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
    elif kind == "agent":
        out["profile"] = _pick(event.get("profile"), _PROFILE_KEYS)
    return out


def project_result(result: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if result is None:
        return None
    return _narrow_verdict(result, _RESULT_KEYS)


def stored_result(result: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The result as `runs.verdict` keeps it: the served keys, plus the backend-only report keys.

    Serving always goes through project_result; this is the only place the backend-only keys are kept.
    """
    if result is None:
        return None
    kept = _pick(result, _BACKEND_RESULT_KEYS)
    return {**(project_result(result) or {}), **kept}
