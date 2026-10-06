"""Tests for normalization module."""
import asyncio
import itertools

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.graph.normalization import (
    EntityNode,
    RelationEdge,
    normalize_and_write,
    GraphNormalizationStage,
    MergeCandidate,
)


class TestEntityNode:
    """Tests for EntityNode dataclass."""

    def test_auto_generates_id(self):
        """Verify id is auto-generated when not provided."""
        entity = EntityNode(labels=["Person"], properties={"name": "Alice"})
        assert entity.id is not None
        assert len(entity.id) == 36  # UUID format

    def test_uses_provided_id(self):
        """Verify provided id is used."""
        entity = EntityNode(id="custom-id", labels=["Person"])
        assert entity.id == "custom-id"

    def test_default_labels_empty(self):
        """Verify default labels is empty list."""
        entity = EntityNode()
        assert entity.labels == []

    def test_default_properties_empty(self):
        """Verify default properties is empty dict."""
        entity = EntityNode()
        assert entity.properties == {}


class TestRelationEdge:
    """Tests for RelationEdge dataclass."""

    def test_requires_source_and_target(self):
        """Verify source_id and target_id are required."""
        rel = RelationEdge(
            source_id="entity-1",
            target_id="entity-2",
            relation_type="KNOWS"
        )
        assert rel.source_id == "entity-1"
        assert rel.target_id == "entity-2"
        assert rel.relation_type == "KNOWS"

    def test_default_properties_empty(self):
        """Verify default properties is empty dict."""
        rel = RelationEdge(source_id="a", target_id="b", relation_type="REL")
        assert rel.properties == {}


class TestNormalizeAndWrite:
    """Tests for normalize_and_write function."""

    @pytest.mark.asyncio
    async def test_returns_graph_id(self):
        """Verify function returns a valid graph_id."""
        entities = [EntityNode(id="e1", labels=["Person"], properties={"name": "Alice"})]
        relations = []

        with patch.object(GraphNormalizationStage, 'validate_entities', new_callable=AsyncMock) as mock_validate:
            mock_validate.return_value = []
            with patch.object(GraphNormalizationStage, 'validate_relations', new_callable=AsyncMock) as mock_rel_validate:
                mock_rel_validate.return_value = []
                with patch.object(GraphNormalizationStage, 'write_all', new_callable=AsyncMock) as mock_write:
                    mock_write.return_value = ([], 0)
                    with patch.object(GraphNormalizationStage, 'close', new_callable=AsyncMock):
                        graph_id = await normalize_and_write(entities, relations)

        assert graph_id is not None
        assert len(graph_id) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_merges_duplicate_entities(self):
        """Verify duplicate entities are merged by id via normalize_and_write."""
        entities = [
            EntityNode(id="e1", labels=["Person"], properties={"name": "Alice", "age": 30}),
            EntityNode(id="e1", labels=["Person"], properties={"age": 31}),  # duplicate
        ]
        relations = []

        with patch.object(GraphNormalizationStage, 'validate_entities', new_callable=AsyncMock) as mock_validate:
            mock_validate.return_value = []
            with patch.object(GraphNormalizationStage, 'validate_relations', new_callable=AsyncMock) as mock_rel_validate:
                mock_rel_validate.return_value = []
                with patch.object(GraphNormalizationStage, 'write_all', new_callable=AsyncMock) as mock_write:
                    mock_write.return_value = ([], 0)
                    with patch.object(GraphNormalizationStage, 'close', new_callable=AsyncMock):
                        graph_id = await normalize_and_write(entities, relations)

        # Verify write_all was called with merged entities (should have only 1 entity)
        mock_write.assert_called_once()
        call_args = mock_write.call_args
        merged_entities_arg = call_args[0][0]  # First positional arg
        assert len(merged_entities_arg) == 1, "Duplicate entities should be merged into 1"
        assert merged_entities_arg[0].id == "e1"
        assert merged_entities_arg[0].properties["name"] == "Alice"
        # Merge fills in missing values; existing values are preserved (age=30 from first entity)
        assert merged_entities_arg[0].properties["age"] == 30

    @pytest.mark.asyncio
    async def test_validates_entities(self):
        """Verify entity validation is called."""
        entities = [EntityNode(id="e1", labels=["Person"])]
        relations = []

        with patch.object(GraphNormalizationStage, 'validate_entities', new_callable=AsyncMock) as mock_validate:
            mock_validate.return_value = []
            with patch.object(GraphNormalizationStage, 'validate_relations', new_callable=AsyncMock) as mock_rel_validate:
                mock_rel_validate.return_value = []
                with patch.object(GraphNormalizationStage, 'write_all', new_callable=AsyncMock) as mock_write:
                    mock_write.return_value = ([], 0)
                    with patch.object(GraphNormalizationStage, 'close', new_callable=AsyncMock):
                        await normalize_and_write(entities, relations)

        mock_validate.assert_called_once_with(entities)

    @pytest.mark.asyncio
    async def test_raises_on_validation_error(self):
        """Verify ValueError is raised when validation fails."""
        entities = [EntityNode(id="e1", labels=["Person"])]
        relations = []

        with patch.object(GraphNormalizationStage, 'validate_entities', new_callable=AsyncMock) as mock_validate:
            mock_validate.return_value = ["Entity e1: must have at least one label"]

            with pytest.raises(ValueError, match="Entity validation errors"):
                await normalize_and_write(entities, relations)


class TestGraphNormalizationStageValidation:
    """Tests for GraphNormalizationStage validation methods."""

    @pytest.mark.asyncio
    async def test_validate_entities_accepts_valid(self):
        """Verify validation passes for valid entities."""
        config = MagicMock()
        config.neo4j_uri = "bolt://localhost:7687"
        config.neo4j_username = "neo4j"
        config.neo4j_password = "password"
        config.neo4j_database = "neo4j"

        with patch('src.graph.normalization.AsyncGraphDatabase'):
            stage = GraphNormalizationStage(config)
            entities = [EntityNode(id="e1", labels=["Person"])]
            errors = await stage.validate_entities(entities)
            assert errors == []

    @pytest.mark.asyncio
    async def test_validate_entities_rejects_empty_labels(self):
        """Verify validation fails for entities without labels."""
        config = MagicMock()
        config.neo4j_uri = "bolt://localhost:7687"
        config.neo4j_username = "neo4j"
        config.neo4j_password = "password"
        config.neo4j_database = "neo4j"

        with patch('src.graph.normalization.AsyncGraphDatabase'):
            stage = GraphNormalizationStage(config)
            entities = [EntityNode(id="e1", labels=[])]
            errors = await stage.validate_entities(entities)
            assert len(errors) > 0
            assert "must have at least one label" in errors[0]

    @pytest.mark.asyncio
    async def test_validate_relations_accepts_valid(self):
        """Verify validation passes for valid relations."""
        config = MagicMock()
        config.neo4j_uri = "bolt://localhost:7687"
        config.neo4j_username = "neo4j"
        config.neo4j_password = "password"
        config.neo4j_database = "neo4j"

        with patch('src.graph.normalization.AsyncGraphDatabase'):
            stage = GraphNormalizationStage(config)
            relations = [RelationEdge(source_id="e1", target_id="e2", relation_type="KNOWS")]
            valid_ids = ["e1", "e2"]
            errors = await stage.validate_relations(relations, valid_ids)
            assert errors == []

    @pytest.mark.asyncio
    async def test_validate_relations_rejects_unknown_entity(self):
        """Verify validation fails for relations with unknown entity IDs."""
        config = MagicMock()
        config.neo4j_uri = "bolt://localhost:7687"
        config.neo4j_username = "neo4j"
        config.neo4j_password = "password"
        config.neo4j_database = "neo4j"

        with patch('src.graph.normalization.AsyncGraphDatabase'):
            stage = GraphNormalizationStage(config)
            relations = [RelationEdge(source_id="e1", target_id="e2", relation_type="KNOWS")]
            valid_ids = ["e1"]  # e2 is missing
            errors = await stage.validate_relations(relations, valid_ids)
            assert len(errors) > 0
            assert "e2" in errors[0]


class TestMergeCandidate:
    """Tests for MergeCandidate dataclass."""

    def test_creation(self):
        """Verify MergeCandidate creation."""
        candidate = MergeCandidate(
            node_id=123,
            labels=["Person", "Employee"],
            properties={"name": "Bob", "department": "Engineering"}
        )
        assert candidate.node_id == 123
        assert candidate.labels == ["Person", "Employee"]
        assert candidate.properties["name"] == "Bob"


class _FakeAsyncResult:
    """Minimal async-iterable stand-in for a Neo4j Result."""

    def __init__(self, records):
        self._records = records

    async def __aiter__(self):
        for record in self._records:
            yield record


class TestFindSurfaceDuplicates:
    """Regression tests for surface-duplicate detection keyed by elementId."""

    @pytest.mark.asyncio
    async def test_duplicate_group_with_string_element_ids(self):
        """Neo4j 5 elementId() returns a string ("4:abc:123") — duplicate groups must not int() it."""
        config = MagicMock()
        config.neo4j_uri = "bolt://localhost:7687"
        config.neo4j_username = "neo4j"
        config.neo4j_password = "password"
        config.neo4j_database = "neo4j"

        with patch('src.graph.normalization.AsyncGraphDatabase'):
            stage = GraphNormalizationStage(config)

        records = [{
            "key": "alice",
            "nodes": [
                {"id": "4:abc:123", "labels": ["Person"], "props": {"name": "Alice", "source": "doc-a"}},
                {"id": "4:abc:456", "labels": ["Person"], "props": {"name": "Alice", "source": "doc-b"}},
            ],
        }]
        stage._run = AsyncMock(return_value=_FakeAsyncResult(records))

        groups = await stage.find_surface_duplicates("ds-1")

        assert len(groups) == 1
        assert [c.node_id for c in groups[0]] == ["4:abc:123", "4:abc:456"]
        assert all(isinstance(c.node_id, str) for c in groups[0])


class TestPairScoringConcurrency:
    """Pair scoring fans out concurrently under a fixed in-flight bound."""

    GROUP_SIZE = 4  # -> 6 candidate pairs
    LIMIT = 2

    def _stage(self) -> GraphNormalizationStage:
        config = MagicMock()
        config.neo4j_uri = "bolt://localhost:7687"
        config.neo4j_username = "neo4j"
        config.neo4j_password = "password"
        config.neo4j_database = "neo4j"
        config.ontology_max_concurrency = self.LIMIT
        with patch('src.graph.normalization.AsyncGraphDatabase'):
            return GraphNormalizationStage(config)

    def _instrument(self, stage: GraphNormalizationStage) -> dict:
        """Swap the per-pair network scorer for a recorder of overlap."""
        state = {"in_flight": 0, "max_in_flight": 0, "calls": []}

        async def recording_jaccard(id_a, id_b):
            state["in_flight"] += 1
            state["max_in_flight"] = max(state["max_in_flight"], state["in_flight"])
            state["calls"].append((id_a, id_b))
            await asyncio.sleep(0.01)
            state["in_flight"] -= 1
            return 0.5

        stage._neighbor_label_jaccard = recording_jaccard
        stage._embedding_similarity = AsyncMock(return_value=0.0)
        return state

    def _group(self):
        return [
            MergeCandidate(node_id=f"4:abc:{i}", labels=["Person"], properties={"name": f"n{i}"})
            for i in range(self.GROUP_SIZE)
        ]

    def _expected_pairs(self):
        return [
            (f"4:abc:{i}", f"4:abc:{j}")
            for i, j in itertools.combinations(range(self.GROUP_SIZE), 2)
        ]

    @pytest.mark.asyncio
    async def test_never_exceeds_configured_concurrency(self):
        """In-flight pair scoring never exceeds ontology_max_concurrency."""
        stage = self._stage()
        state = self._instrument(stage)

        await stage.compute_signals(self._group())

        assert state["max_in_flight"] <= self.LIMIT

    @pytest.mark.asyncio
    async def test_scores_pairs_concurrently(self):
        """Pairs overlap in flight — scoring is not one-at-a-time."""
        stage = self._stage()
        state = self._instrument(stage)

        await stage.compute_signals(self._group())

        assert state["max_in_flight"] > 1

    @pytest.mark.asyncio
    async def test_scores_every_pair_exactly_once(self):
        """Every pair is scored exactly once despite concurrency."""
        stage = self._stage()
        state = self._instrument(stage)

        await stage.compute_signals(self._group())

        assert sorted(state["calls"]) == self._expected_pairs()

    @pytest.mark.asyncio
    async def test_preserves_pair_order_in_signals(self):
        """signals['pairs'] keeps itertools.combinations order."""
        stage = self._stage()
        self._instrument(stage)

        signals = await stage.compute_signals(self._group())

        assert [(p["a"], p["b"]) for p in signals["pairs"]] == self._expected_pairs()
