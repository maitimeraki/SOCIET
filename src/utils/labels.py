"""The one cap on a report source label: control characters removed, then capped.

Titles, sections and breadcrumbs are short labels. The simulation layer caps them when it stores
the report's sources, and the API layer caps them again when it serves them, so both import this
module rather than copy the rule.
"""

import re
from collections.abc import Mapping
from typing import Any

TEXT_MAX_CHARS = 200
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def label_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return _CONTROL_CHARS.sub("", value)[:TEXT_MAX_CHARS]


def public_source(source: Any) -> dict[str, str] | None:
    """One source as {document, section}, both labels capped. Anything else is None."""
    if not isinstance(source, Mapping):
        return None
    document, section = label_text(source.get("document")), label_text(source.get("section"))
    if document is None or section is None:
        return None
    return {"document": document, "section": section}
