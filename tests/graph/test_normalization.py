"""Tests for normalization module."""
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
