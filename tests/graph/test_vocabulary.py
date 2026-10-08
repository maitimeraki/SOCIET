"""Tests for bounded vocabulary discovery from a spread sample."""
import pytest

from src.graph.models_graph import (
    EntityTypeDefinition,
    OntologyMetadata,
    LocalOntology,
    ProcessedChunk,
    RelationTypeDefinition,
)
from src.graph.vocabulary import (
    discover_vocabulary,
    promote,
    select_slice,
    spread_indexes,
)


def _chunk(i: int) -> ProcessedChunk:
    return ProcessedChunk(
        chunk_id=f"chunk-{i}",
        parent_doc_id="doc-1",
        chunk_index=i,
        content_hash=f"hash{i}",
        content=f"Chunk body number {i}.",
        summary_context="Software architecture overview",
        breadcrumb="docs/architecture",
        header_level=1,
        domain_tags=["software"],
        expertise_level="Technical",
        metadata={"title": "System Architecture"},
    )


def _ontology_with_labels(n: int) -> LocalOntology:
    return LocalOntology(
        metadata=OntologyMetadata(),
        entity_types=[EntityTypeDefinition(type_name=f"Type{i}") for i in range(n)],
        relation_types=[],
    )


class _CapturingStage:
    """Stand-in for OntologyDiscoveryStage: records the documents it receives."""

    def __init__(self, ontology: LocalOntology):
        self.ontology = ontology
        self.seen = None
        self.sample_size = None

    async def run(self, documents, sample_size):
        self.seen = list(documents)
        self.sample_size = sample_size
        return self.ontology


class TestSpreadIndexes:
    def test_spread_includes_first_and_last(self):
        assert spread_indexes(30, 6) == [0, 6, 12, 17, 23, 29]

    def test_spread_single_sample_does_not_divide_by_zero(self):
        assert spread_indexes(30, 1) == [0]

    def test_spread_more_samples_than_docs_returns_all(self):
        assert spread_indexes(3, 10) == [0, 1, 2]

    def test_spread_empty_corpus(self):
        assert spread_indexes(0, 6) == []


class TestDiscoverVocabularySpread:
    @pytest.mark.asyncio
    async def test_spread_sample_covers_endpoints_and_trims_labels(self):
        docs = [_chunk(i) for i in range(30)]
        stage = _CapturingStage(_ontology_with_labels(300))

        result = await discover_vocabulary(docs, sample_size=6, max_labels=200, stage=stage)

        # Exactly sample_size chunks reach the single discovery call.
        assert len(stage.seen) == 6
        # Spread over the corpus, endpoints inclusive (first and last chunk).
        indexes = [c.chunk_index for c in stage.seen]
        assert indexes == [0, 6, 12, 17, 23, 29]
        assert indexes[0] == 0
        assert indexes[-1] == 29
        # The whole sample survives the stage's own `documents[:sample_size]` cut.
        assert stage.sample_size == 6
        # Entity types are bounded to max_labels.
        assert len(result.entity_types) == 200

    @pytest.mark.asyncio
    async def test_spread_makes_exactly_one_discovery_call(self):
        docs = [_chunk(i) for i in range(10)]
        stage = _CapturingStage(_ontology_with_labels(5))

        await discover_vocabulary(docs, sample_size=4, max_labels=200, stage=stage)

        assert len(stage.seen) == 4

    @pytest.mark.asyncio
    async def test_spread_leaves_smaller_label_sets_untouched(self):
        docs = [_chunk(i) for i in range(10)]
        stage = _CapturingStage(_ontology_with_labels(3))

        result = await discover_vocabulary(docs, sample_size=4, max_labels=200, stage=stage)

        assert len(result.entity_types) == 3


def _ontology_with_named_labels(entity_labels, relation_labels=()) -> LocalOntology:
    return LocalOntology(
        metadata=OntologyMetadata(),
        entity_types=[EntityTypeDefinition(type_name=n) for n in entity_labels],
        relation_types=[RelationTypeDefinition(type_name=n) for n in relation_labels],
    )


class TestSelectSlice:
    def test_slice_keeps_mentioned_labels_within_k(self):
        vocab = _ontology_with_named_labels(
            ["Microservice", "Database", "Kafka", "Kubernetes", "Redis", "Postgres"]
        )
        chunk = "The Microservice publishes events to Kafka on every write."

        result = select_slice(vocab, chunk, k=3)

        labels = result.entity_labels + result.relation_labels
        assert len(labels) <= 3
        assert "Microservice" in labels
        assert "Kafka" in labels

    def test_slice_ranks_entity_and_relation_labels_together(self):
        vocab = _ontology_with_named_labels(
            ["Microservice", "Database"],
            ["Kafka", "Owns"],
        )
        chunk = "Each Database row is read by Kafka consumers."

        result = select_slice(vocab, chunk, k=2)

        assert len(result.entity_labels) + len(result.relation_labels) <= 2
        assert "Database" in result.entity_labels
        assert "Kafka" in result.relation_labels

    def test_slice_returns_vocabulary_unchanged_when_not_larger_than_k(self):
        vocab = _ontology_with_named_labels(["Microservice", "Kafka"])

        assert select_slice(vocab, "Microservice writes to Kafka", k=8) is vocab


class TestPromote:
    def test_promote_adds_only_labels_not_yet_present(self):
        vocab = _ontology_with_named_labels(["Person"])

        updated, newly_added = promote(vocab, ["Molecule", "Person"])

        assert sorted(updated.entity_labels) == ["Molecule", "Person"]
        assert newly_added == ["Molecule"]

    def test_promote_known_label_is_a_noop(self):
        vocab = _ontology_with_named_labels(["Person"])

        updated, newly_added = promote(vocab, ["Person"])

        assert updated.entity_labels == ["Person"]
        assert newly_added == []

    def test_promote_label_already_present_as_relation_is_a_noop(self):
        vocab = _ontology_with_named_labels(["Person"], ["Works_At"])

        updated, newly_added = promote(vocab, ["Works_At"])

        assert newly_added == []
        assert updated.relation_labels == ["Works_At"]

    def test_promote_skips_blank_labels(self):
        vocab = _ontology_with_named_labels(["Person"])

        updated, newly_added = promote(vocab, ["", "   "])

        assert newly_added == []
        assert updated.entity_labels == ["Person"]

    def test_promote_relation_kind_lands_in_relation_types(self):
        vocab = _ontology_with_named_labels(["Person"])

        updated, newly_added = promote(vocab, ["ACQUIRED"], kind="relation")

        assert newly_added == ["ACQUIRED"]
        assert updated.relation_labels == ["ACQUIRED"]
        assert "ACQUIRED" not in updated.entity_labels

    def test_promote_entity_then_relation_does_not_duplicate(self):
        vocab = _ontology_with_named_labels([])

        once, _ = promote(vocab, ["Widget"], kind="entity")
        twice, newly_added = promote(once, ["Widget"], kind="relation")

        assert newly_added == []
        assert twice.entity_labels == ["Widget"]
        assert twice.relation_labels == []

    def test_promote_unknown_kind_is_rejected(self):
        vocab = _ontology_with_named_labels(["Person"])

        with pytest.raises(ValueError):
            promote(vocab, ["Widget"], kind="banana")


class TestProposedLabels:
    def test_collector_splits_kinds_and_drops_default_entity_label(self):
        from llama_index.core.graph_stores.types import (
            EntityNode,
            KG_NODES_KEY,
            KG_RELATIONS_KEY,
            Relation,
        )
        from llama_index.core.schema import TextNode

        from src.graph.graph_build import _proposed_labels

        chunk = TextNode(
            text="ACME acquired Beta.",
            metadata={
                KG_NODES_KEY: [
                    EntityNode(name="ACME", label="Organization"),
                    EntityNode(name="Beta"),  # simple extractor: label defaults to "entity"
                ],
                KG_RELATIONS_KEY: [
                    Relation(label="ACQUIRED", source_id="a", target_id="b"),
                ],
            },
        )

        entity_labels, relation_labels = _proposed_labels([chunk])

        assert entity_labels == ["Organization"]
        assert relation_labels == ["ACQUIRED"]
