"""One bounded vocabulary per dataset, discovered once from a spread sample.

Per-chunk discovery + union made the label list grow with document size, which
then bloated every later prompt. Here a single discovery call runs over a
sample spread evenly across the corpus — endpoints inclusive — and the entity
types are trimmed to a fixed ceiling.
"""
import logging
import re
from typing import List, Optional

from src.graph.config_graph import GraphConfig
from src.graph.models_graph import (
    EntityTypeDefinition,
    LocalOntology,
    ProcessedChunk,
    RelationTypeDefinition,
)
from src.graph.ontology import OntologyDiscoveryStage

logger = logging.getLogger(__name__)


def spread_indexes(n: int, k: int) -> List[int]:
    """Evenly spread `k` sample indexes across `n` items, endpoints inclusive.

    For `n` items and `k` samples the chosen indexes are
    ``round(i * (n - 1) / (k - 1))`` for ``i`` in ``0..k-1`` — always including
    both ``0`` and ``n-1``. Returns every index when ``k >= n``, and ``[0]``
    when only one sample is asked for (no division by zero).
    """
    if n <= 0:
        return []
    if k <= 1:
        return [0]
    if k >= n:
        return list(range(n))
    return sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})


async def discover_vocabulary(
    documents: List[ProcessedChunk],
    sample_size: int,
    max_labels: int,
    stage: Optional[OntologyDiscoveryStage] = None,
) -> LocalOntology:
    """Discover ONE vocabulary from a spread sample of `documents`.

    The sample is pre-selected here and passed whole to the discovery stage, so
    the stage's own ``documents[:sample_size]`` truncation cannot drop the tail.
    Entity types are trimmed to `max_labels`.
    """
    if stage is None:
        cfg = GraphConfig()
        stage = OntologyDiscoveryStage(
            model=cfg.discovery_model,
            temperature=cfg.temperature,
            timeout=min(60.0, cfg.discovery_timeout_seconds),
        )

    sample = [documents[i] for i in spread_indexes(len(documents), sample_size)]
    ontology = await stage.run(documents=sample, sample_size=max(1, len(sample)))

    if max_labels is not None and len(ontology.entity_types) > max_labels:
        logger.info(
            "Trimming discovered vocabulary from %d to %d entity types",
            len(ontology.entity_types),
            max_labels,
        )
        ontology.entity_types = ontology.entity_types[:max_labels]

    return ontology


def select_slice(vocabulary: LocalOntology, chunk_text: str, k: int) -> LocalOntology:
    """The `k` labels most relevant to `chunk_text`, as a `LocalOntology`.

    Keyword / exact-mention overlap between the chunk and each label (name plus
    description) is the whole score — deterministic and offline. A label whose
    name occurs in the chunk (case-insensitive) always outranks one that does
    not, so it is included whenever `k` allows.

    ponytail: no embedding cosine — the chunk-slice decision is a lexical one
    and the embed model is a live network hop. Add cosine blending when the
    lexical ranking measurably picks the wrong labels.
    """
    labeled = [
        (index, "entity", name, definition)
        for index, name, definition in _labels(vocabulary.entity_types)
    ] + [
        (index, "relation", name, definition)
        for index, name, definition in _labels(vocabulary.relation_types)
    ]
    if len(labeled) <= k:
        return vocabulary

    haystack = chunk_text.lower()
    chunk_words = set(re.findall(r"\w+", haystack))

    def relevance(name: str, description: str) -> float:
        lowered = name.lower()
        score = 100.0 if lowered and lowered in haystack else 0.0
        score += len(set(re.findall(r"\w+", lowered)) & chunk_words)
        score += 0.5 * len(set(re.findall(r"\w+", description.lower())) & chunk_words)
        return score

    ranked = sorted(
        labeled,
        key=lambda row: (-relevance(row[2], row[3].description), row[0]),
    )

    keep = {(kind, index) for index, kind, _, _ in ranked[:k]}
    return LocalOntology(
        metadata=vocabulary.metadata,
        entity_types=[
            e for index, e in enumerate(vocabulary.entity_types) if ("entity", index) in keep
        ],
        relation_types=[
            r for index, r in enumerate(vocabulary.relation_types) if ("relation", index) in keep
        ],
    )


def promote(
    vocabulary: LocalOntology,
    proposed: List[str],
    kind: str = "entity",
) -> tuple[LocalOntology, List[str]]:
    """Add every proposed label the vocabulary does not already carry.

    Exact-string match only: a proposal equal to an existing entity OR relation
    label is a no-op, and fuzzy merging stays `GraphNormalizationStage`'s job.
    Returns the updated vocabulary — the SAME object when nothing is new — plus
    the newly-added labels, in proposal order and de-duplicated.

    `kind` ("entity" or "relation") picks which side the new labels join, each as
    a property-less type definition, so a relation label never becomes an entity
    type and vice versa. It defaults to "entity", keeping the original
    two-argument contract. An unknown kind raises `ValueError` rather than
    silently filing the label under the wrong side.
    """
    if kind not in ("entity", "relation"):
        raise ValueError(f"promote: kind must be 'entity' or 'relation', got {kind!r}")

    known = set(vocabulary.entity_labels) | set(vocabulary.relation_labels)
    newly_added = [
        label
        for label in dict.fromkeys(proposed)
        if label.strip() and label not in known
    ]
    if not newly_added:
        return vocabulary, []

    entity_types, relation_types = vocabulary.entity_types, vocabulary.relation_types
    if kind == "relation":
        relation_types = relation_types + [
            RelationTypeDefinition(type_name=label) for label in newly_added
        ]
    else:
        entity_types = entity_types + [
            EntityTypeDefinition(type_name=label) for label in newly_added
        ]
    return (
        LocalOntology(
            metadata=vocabulary.metadata,
            entity_types=entity_types,
            relation_types=relation_types,
        ),
        newly_added,
    )


def _labels(definitions):
    """(position, name, definition) for the non-blank-named types, in order."""
    for index, definition in enumerate(definitions):
        name = definition.type_name
        if name and name.strip():
            yield index, name, definition
