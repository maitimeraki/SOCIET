"""Loaders and format checks for the golden-set files. No graph or LLM access."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GOLDEN_DIR = Path(__file__).parent
QUESTIONS_PATH = GOLDEN_DIR / "questions.json"
TARGETS_PATH = GOLDEN_DIR / "targets.json"
STANCES = frozenset({"POSITIVE", "NEGATIVE", "NEUTRAL", "ABSTAIN"})
TARGET_KEYS = ("ndcg_at_10", "recall_at_n", "brier_max")
# Rows whose dataset starts with this prefix are the shipped samples, not a labelled set.
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
    relevant = row["relevant"]
    if not isinstance(relevant, dict) or not all(
        isinstance(label, int) and not isinstance(label, bool) and 0 <= label <= 3 for label in relevant.values()
    ):
        raise ValueError(f"{where}: relevant must map entity names to integer labels 0-3")
    if not any(label > 0 for label in relevant.values()):
        raise ValueError(f"{where}: at least one entity must be labelled relevant (label > 0)")
    stance = row["stance"]
    if not isinstance(stance, dict) or not all(value in STANCES for value in stance.values()):
        raise ValueError(f"{where}: stance values must be one of {sorted(STANCES)}")
    return Question(row["dataset"], row["question"], dict(relevant), dict(stance))


def is_sample_only(questions: list[Question]) -> bool:
    return all(q.dataset.startswith(SAMPLE_DATASET_PREFIX) for q in questions)


def load_targets(path: Path = TARGETS_PATH) -> dict[str, float | None]:
    targets = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(targets, dict) or set(targets) != set(TARGET_KEYS):
        raise ValueError(f"{path.name}: expected exactly the keys {list(TARGET_KEYS)}")
    for key, value in targets.items():
        if value is not None and not isinstance(value, (int, float)):
            raise ValueError(f"{path.name}: {key} must be a number or null")
    return targets
