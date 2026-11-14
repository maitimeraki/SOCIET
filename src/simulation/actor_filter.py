"""Actor filter: one metered LLM call classifying entity type labels as actors."""

from __future__ import annotations

import json
import logging
from typing import Sequence

from src.billing import metering
from src.llm.config_llm import get_llm_config
from src.simulation.verdict import _extract_json_object

logger = logging.getLogger(__name__)

ACTOR_SYSTEM_PROMPT = (
    "Classify each entity type label. An ACTOR can hold a position in a debate: "
    "a person, organisation, product, regulator, market participant. A metric, "
    "quantity, date, category or attribute is not an actor. Reply with ONLY a "
    "JSON object mapping each label to true or false."
)


def _all_actors(labels: Sequence[str]) -> tuple[dict[str, bool], bool]:
    return {label: True for label in labels}, True


def _parse_flags(raw: str, labels: Sequence[str]) -> tuple[dict[str, bool], bool] | None:
    candidate = _extract_json_object(raw)
    if candidate is None:
        return None
    try:
        reply = json.loads(candidate)
    except ValueError:
        return None
    if not isinstance(reply, dict):
        return None
    flags: dict[str, bool] = {}
    degraded = False
    for label in labels:
        value = reply.get(label)
        if isinstance(value, bool):
            flags[label] = value
        else:
            flags[label] = True
            degraded = True
    return flags, degraded


async def classify_actor_labels(
    client, labels: Sequence[str]
) -> tuple[dict[str, bool], bool]:
    """Return (label -> is_actor, degraded). Labels the model fails to classify
    count as actors and set degraded; MeteringError is always re-raised."""
    labels = list(labels)
    cfg = get_llm_config()
    with metering.source_scope("debate"):
        try:
            raw = await client.generate(
                system_prompt=ACTOR_SYSTEM_PROMPT,
                user_prompt=json.dumps(labels),
                temperature=0,
                max_tokens=400,
                model=cfg.analysis_model,
            )
        except metering.MeteringError:
            raise
        except Exception:
            logger.exception("actor filter call failed; treating all labels as actors")
            return _all_actors(labels)
    parsed = _parse_flags(raw, labels)
    if parsed is None:
        logger.warning("actor filter reply had no parseable JSON; treating all labels as actors")
        return _all_actors(labels)
    return parsed
