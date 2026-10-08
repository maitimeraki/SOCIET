"""One bounded vocabulary per dataset, discovered once from a spread sample.

Per-chunk discovery + union made the label list grow with document size, which
then bloated every later prompt. Here a single discovery call runs over a
sample spread evenly across the corpus — endpoints inclusive — and the entity
types are trimmed to a fixed ceiling.
"""
import logging
from typing import List, Optional

from src.graph.config_graph import GraphConfig
from src.graph.models_graph import LocalOntology, ProcessedChunk
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
