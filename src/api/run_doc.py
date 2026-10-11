"""Run-document store for debate runs: persistence + history (§12.4).

The file is the durable mirror of the live in-memory job; it is rewritten as
the run broadcasts (throttled per run — see `debate_api._persist_debate_run`),
so a hard crash loses at most the events since the last write.
"""
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

RUNS_DIR = Path("src/api/runtime/debates")

logger = logging.getLogger(__name__)


def _path(run_id: str) -> Path:
    return RUNS_DIR / f"{run_id}.json"


def write_run_doc(doc: dict[str, Any]) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = _path(doc["run_id"])
    # Temp file + os.replace: a crash mid-write loses at most the in-flight event,
    # never tears the JSON (§19.3).
    tmp = path.with_suffix(".json.tmp")
    # Compact (separators, no indent): the doc is machine-read, not human-diffed.
    tmp.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


def read_run_doc(run_id: str) -> Optional[dict[str, Any]]:
    path = _path(run_id)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        # Missing, unreadable, or corrupt — degrade to "not found", matching
        # `list_run_docs`, rather than raising out of the route.
        logger.warning("could not read run doc %s: %s", run_id, exc)
        return None


def list_run_docs() -> list[dict[str, Any]]:
    if not RUNS_DIR.exists():
        return []
    docs: list[dict[str, Any]] = []
    for path in RUNS_DIR.glob("*.json"):
        try:
            # ValueError covers both bad JSON and undecodable bytes (UnicodeDecodeError).
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("skipping unreadable run doc %s: %s", path, exc)
            continue
        if not isinstance(doc, dict):
            logger.warning("skipping non-document run file %s", path)
            continue
        docs.append(doc)
    return sorted(docs, key=lambda doc: doc.get("created_at") or "", reverse=True)
