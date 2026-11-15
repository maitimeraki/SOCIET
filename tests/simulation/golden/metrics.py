"""Golden-set metrics for the seat ranking. Pure stdlib, no I/O.

Gains are exponential: an entity labelled `rel` (0-3) contributes `2**rel - 1`
(so 0, 1, 3, 7), discounted by `log2(position + 1)` with positions counted from 1.
Label 0 means not relevant. Recall counts an entity as relevant when its label is
above 0. Brier is the mean squared error of a probability against a 0/1 outcome.
"""

import math
from collections.abc import Mapping, Sequence


def _dcg(labels: Sequence[int]) -> float:
    return sum((2**label - 1) / math.log2(position + 1) for position, label in enumerate(labels, start=1))


def ndcg_at_k(ranked: Sequence[str], relevant: Mapping[str, int], k: int = 10) -> float:
    """NDCG@k in [0, 1]. Returns 0.0 when nothing is labelled relevant (the ideal DCG is zero).

    A k larger than the ranking scores the whole ranking. Entities missing from `relevant`
    count as label 0.
    """
    if k < 1:
        raise ValueError("k must be at least 1")
    ideal = _dcg(sorted((r for r in relevant.values() if r > 0), reverse=True)[:k])
    if ideal == 0.0:
        return 0.0
    return _dcg([relevant.get(entity, 0) for entity in ranked[:k]]) / ideal


def recall_at_n(ranked: Sequence[str], relevant: Mapping[str, int], n: int) -> float:
    """Share of the entities labelled relevant (label > 0) that appear in the top n.

    Returns 0.0 when nothing is labelled relevant, so the question adds no credit.
    """
    if n < 1:
        raise ValueError("n must be at least 1")
    relevant_set = {entity for entity, label in relevant.items() if label > 0}
    if not relevant_set:
        return 0.0
    return len(relevant_set.intersection(ranked[:n])) / len(relevant_set)


def brier(pairs: Sequence[tuple[float, bool]]) -> float:
    """Mean squared error of forecast probabilities against outcomes; 0.0 is perfect.

    A constant 0.5 forecast scores 0.25. Raises ValueError on an empty sequence (there is
    nothing to score) or a probability outside [0, 1].
    """
    if not pairs:
        raise ValueError("brier needs at least one (probability, outcome) pair")
    total = 0.0
    for probability, outcome in pairs:
        if not 0.0 <= probability <= 1.0:
            raise ValueError(f"probability {probability!r} is outside [0, 1]")
        total += (probability - float(outcome)) ** 2
    return total / len(pairs)
