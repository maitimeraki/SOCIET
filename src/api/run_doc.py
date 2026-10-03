"""Run-document store for debate runs: persistence + history (§12.4).

The file is the durable mirror of the live in-memory job; it is rewritten on
every broadcast, so a hard crash loses at most the in-flight event.
"""
import json
from pathlib import Path
from typing import Any, Optional

RUNS_DIR = Path("src/api/runtime/debates")


def _path(run_id: str) -> Path:
    return RUNS_DIR / f"{run_id}.json"


def write_run_doc(doc: dict[str, Any]) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    _path(doc["run_id"]).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def read_run_doc(run_id: str) -> Optional[dict[str, Any]]:
    path = _path(run_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_run_docs() -> list[dict[str, Any]]:
    if not RUNS_DIR.exists():
        return []
    docs = [json.loads(path.read_text(encoding="utf-8")) for path in RUNS_DIR.glob("*.json")]
    return sorted(docs, key=lambda doc: doc.get("created_at") or "", reverse=True)
