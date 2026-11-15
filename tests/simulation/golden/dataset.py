"""Loaders and format checks for the golden-set files. No graph or LLM access."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tests.simulation.golden.metrics import check_labels

GOLDEN_DIR = Path(__file__).parent
QUESTIONS_PATH = GOLDEN_DIR / "questions.json"
TARGETS_PATH = GOLDEN_DIR / "targets.json"
STANCES = frozenset({"POSITIVE", "NEGATIVE", "NEUTRAL", "ABSTAIN"})
TARGET_KEYS = ("ndcg_at_10", "recall_at_n", "brier_max")
# Every golden dataset name starts with this. A live run writes persona links into the
# dataset, so a name without it is refused at load: it can never reach the graph.
GOLDEN_PREFIX = "golden-"
# Shipped sample rows use this prefix. They are never seated and never averaged.
SAMPLE_DATASET_PREFIX = "golden-sample-"


@dataclass(frozen=True)
class Question:
    dataset: str
    question: str
    relevant: dict[str, int]
    stance: dict[str, str]


def load_questions(path: Path = QUESTIONS_PATH) -> list[Question]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError(f"{path.name}: expected a list of questions")
    return [_question(row, path.name, index) for index, row in enumerate(rows)]


def _question(row: Any, source: str, index: int) -> Question:
    where = f"{source}[{index}]"
    if not isinstance(row, dict) or not {"dataset", "question", "relevant", "stance"} <= row.keys():
        raise ValueError(f"{where}: needs dataset, question, relevant and stance")
    dataset, question = row["dataset"], row["question"]
    if not isinstance(dataset, str) or not dataset.startswith(GOLDEN_PREFIX):
        raise ValueError(f"{where}: dataset must be a string starting with {GOLDEN_PREFIX!r}, got {dataset!r}")
    if not isinstance(question, str) or not question.strip():
        raise ValueError(f"{where}: question must be a non-empty string")
    relevant = row["relevant"]
    if not isinstance(relevant, dict):
        raise ValueError(f"{where}: relevant must map entity names to labels")
    try:
        check_labels(relevant)
    except ValueError as exc:
        raise ValueError(f"{where}: {exc}") from exc
    if not any(label > 0 for label in relevant.values()):
        raise ValueError(f"{where}: at least one entity must be labelled relevant (label > 0)")
    stance = row["stance"]
    if not isinstance(stance, dict) or not all(value in STANCES for value in stance.values()):
        raise ValueError(f"{where}: stance values must be one of {sorted(STANCES)}")
    if not set(stance) <= set(relevant):
        raise ValueError(f"{where}: stance names {sorted(set(stance) - set(relevant))} are not in relevant")
    return Question(dataset, question, dict(relevant), dict(stance))


def is_sample_only(questions: list[Question]) -> bool:
    return all(q.dataset.startswith(SAMPLE_DATASET_PREFIX) for q in questions)


def require_labelled_set(questions: list[Question]) -> list[Question]:
    """Return the questions for a labelled run. Raises if any sample row is mixed in.

    Sample rows are rejected, not dropped, so a half-replaced file fails loudly instead of
    scoring a run that silently lost rows.
    """
    samples = [q.dataset for q in questions if q.dataset.startswith(SAMPLE_DATASET_PREFIX)]
    if samples:
        raise ValueError(
            f"questions.json mixes {len(samples)} sample row(s) into a labelled set; "
            "remove every golden-sample-* row before a labelled run"
        )
    return questions


def load_targets(path: Path = TARGETS_PATH) -> dict[str, float | None]:
    targets = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(targets, dict) or set(targets) != set(TARGET_KEYS):
        raise ValueError(f"{path.name}: expected exactly the keys {list(TARGET_KEYS)}")
    for key, value in targets.items():
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0:
            raise ValueError(f"{path.name}: {key} must be null or a number in [0, 1], got {value!r}")
    return targets
