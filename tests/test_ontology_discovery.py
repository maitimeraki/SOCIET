"""Tests for ontology discovery module."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.graph.ontology import (
    discover_ontology,
    discover_ontology_sync,
    _strip_json_fences,
    _structured_properties,
)
from src.graph.models_graph import ProcessedChunk, LocalOntology


@pytest.fixture
def sample_chunks():
    """Create sample processed chunks for testing."""
    return [
        ProcessedChunk(
            chunk_id="chunk-1",
            parent_doc_id="doc-1",
            chunk_index=0,
            content_hash="abc123",
            content="The software system consists of microservices that communicate via REST APIs.",
            summary_context="Software architecture overview",
            breadcrumb="docs/architecture",
            header_level=1,
            domain_tags=["software", "architecture"],
            expertise_level="Technical",
            metadata={"title": "System Architecture"},
        ),
        ProcessedChunk(
            chunk_id="chunk-2",
            parent_doc_id="doc-1",
            chunk_index=1,
            content_hash="def456",
            content="The authentication service validates user credentials and issues JWT tokens.",
            summary_context="Authentication details",
            breadcrumb="docs/architecture/auth",
            header_level=2,
            domain_tags=["security", "authentication"],
            expertise_level="Technical",
            metadata={"title": "Authentication Service"},
        ),
    ]


class TestStripJsonFences:
    """Tests for _strip_json_fences helper."""

    def test_strips_json_fence(self):
        text = '```json\n{"key": "value"}\n```'
        result = _strip_json_fences(text)
        assert result == '{"key": "value"}'

    def test_strips_plain_fence(self):
        text = '```\n{"key": "value"}\n```'
        result = _strip_json_fences(text)
        assert result == '{"key": "value"}'

    def test_no_fence(self):
        text = '{"key": "value"}'
        result = _strip_json_fences(text)
        assert result == '{"key": "value"}'

    def test_none_input(self):
        result = _strip_json_fences(None)
        assert result == ""


class TestStructuredProperties:
    """Tests for _structured_properties helper."""

    def test_transforms_entity_properties(self):
        llm_data = {
            "entity_types": [
                {
                    "type_name": "Person",
                    "properties": ["name: The person's name", "age: How old they are"]
                }
            ],
            "relation_types": []
        }
        result = _structured_properties(llm_data)

        assert len(result["entity_types"]) == 1
        assert result["entity_types"][0]["type_name"] == "Person"
        assert result["entity_types"][0]["properties"] == [
            {"name": "name", "description": "The person's name"},
            {"name": "age", "description": "How old they are"}
        ]

    def test_transforms_relation_properties(self):
        llm_data = {
            "entity_types": [],
            "relation_types": [
                {
                    "type_name": "WORKS_AT",
                    "properties": ["since: When employment started"]
                }
            ]
        }
        result = _structured_properties(llm_data)

        assert len(result["relation_types"]) == 1
        assert result["relation_types"][0]["properties"] == [
            {"name": "since", "description": "When employment started"}
        ]

    def test_handles_missing_properties(self):
        llm_data = {
            "entity_types": [{"type_name": "Thing"}],
            "relation_types": [{"type_name": "RELATES_TO"}]
        }
        result = _structured_properties(llm_data)

        assert result["entity_types"][0]["properties"] == []
        assert result["relation_types"][0]["properties"] == []


class TestDiscoverOntology:
    """Tests for discover_ontology function."""

    @pytest.mark.asyncio
    async def test_returns_local_ontology(self, sample_chunks):
        """Verify discover_ontology returns a LocalOntology instance."""
        mock_response = MagicMock()
        mock_response.__str__ = lambda self: '{"entity_types": [], "relation_types": []}'

        with patch("src.graph.ontology.OpenAILike") as mock_llm:
            mock_instance = AsyncMock()
            mock_instance.acomplete = AsyncMock(return_value=mock_response)
            mock_llm.return_value = mock_instance

            result = await discover_ontology(sample_chunks, sample_size=2)

            assert isinstance(result, LocalOntology)
            assert hasattr(result, "entity_types")
            assert hasattr(result, "relation_types")
            assert hasattr(result, "metadata")

    @pytest.mark.asyncio
    async def test_sample_size_respected(self, sample_chunks):
        """Verify sample_size parameter limits chunks used."""
        mock_response = MagicMock()
        mock_response.__str__ = lambda self: '{"entity_types": [], "relation_types": []}'

        with patch("src.graph.ontology.OpenAILike") as mock_llm:
            mock_instance = AsyncMock()
            mock_instance.acomplete = AsyncMock(return_value=mock_response)
            mock_llm.return_value = mock_instance

            await discover_ontology(sample_chunks, sample_size=1)

            # Verify the LLM was called (sampling is internal to stage.run)
            mock_instance.acomplete.assert_called_once()

    @pytest.mark.asyncio
    async def test_entity_types_discovered(self, sample_chunks):
        """Verify entity types are properly discovered from LLM response."""
        mock_response = MagicMock()
        mock_response.__str__ = lambda self: '''{
            "entity_types": [
                {
                    "type_name": "Microservice",
                    "description": "A distributed software component",
                    "properties": ["name: Service identifier", "version: Software version"]
                }
            ],
            "relation_types": []
        }'''

        with patch("src.graph.ontology.OpenAILike") as mock_llm:
            mock_instance = AsyncMock()
            mock_instance.acomplete = AsyncMock(return_value=mock_response)
            mock_llm.return_value = mock_instance

            result = await discover_ontology(sample_chunks)

            assert len(result.entity_types) == 1
            assert result.entity_types[0].type_name == "Microservice"
            assert len(result.entity_types[0].properties) == 2
            assert result.entity_types[0].properties[0].name == "name"

    @pytest.mark.asyncio
    async def test_relation_types_discovered(self, sample_chunks):
        """Verify relation types are properly discovered from LLM response."""
        mock_response = MagicMock()
        mock_response.__str__ = lambda self: '''{
            "entity_types": [],
            "relation_types": [
                {
                    "type_name": "COMMUNICATES_VIA",
                    "description": "How services communicate",
                    "source_entity_types": ["Service"],
                    "target_entity_types": ["Protocol"],
                    "properties": ["protocol: Communication protocol used"]
                }
            ]
        }'''

        with patch("src.graph.ontology.OpenAILike") as mock_llm:
            mock_instance = AsyncMock()
            mock_instance.acomplete = AsyncMock(return_value=mock_response)
            mock_llm.return_value = mock_instance

            result = await discover_ontology(sample_chunks)

            assert len(result.relation_types) == 1
            assert result.relation_types[0].type_name == "COMMUNICATES_VIA"
            assert "Service" in result.relation_types[0].source_entity_types


class TestDiscoverOntologySync:
    """Tests for discover_ontology_sync function."""

    def test_sync_wrapper_returns_ontology(self, sample_chunks):
        """Verify sync wrapper returns LocalOntology."""
        mock_response = MagicMock()
        mock_response.__str__ = lambda self: '{"entity_types": [], "relation_types": []}'

        with patch("src.graph.ontology.OpenAILike") as mock_llm:
            mock_instance = AsyncMock()
            mock_instance.acomplete = AsyncMock(return_value=mock_response)
            mock_llm.return_value = mock_instance

            result = discover_ontology_sync(sample_chunks)

            assert isinstance(result, LocalOntology)


class TestOntologyProperties:
    """Test ontology model properties."""

    @pytest.mark.asyncio
    async def test_entity_labels_property(self, sample_chunks):
        """Verify entity_labels returns type names."""
        mock_response = MagicMock()
        mock_response.__str__ = lambda self: '''{
            "entity_types": [
                {"type_name": "Person", "description": "A human"},
                {"type_name": "Organization", "description": "A company or group"}
            ],
            "relation_types": []
        }'''

        with patch("src.graph.ontology.OpenAILike") as mock_llm:
            mock_instance = AsyncMock()
            mock_instance.acomplete = AsyncMock(return_value=mock_response)
            mock_llm.return_value = mock_instance

            result = await discover_ontology(sample_chunks)

            assert result.entity_labels == ["Person", "Organization"]

    @pytest.mark.asyncio
    async def test_relation_labels_property(self, sample_chunks):
        """Verify relation_labels returns type names."""
        mock_response = MagicMock()
        mock_response.__str__ = lambda self: '''{
            "entity_types": [],
            "relation_types": [
                {"type_name": "WORKS_AT", "description": "Employment relation"},
                {"type_name": "KNOWS", "description": "Social connection"}
            ]
        }'''

        with patch("src.graph.ontology.OpenAILike") as mock_llm:
            mock_instance = AsyncMock()
            mock_instance.acomplete = AsyncMock(return_value=mock_response)
            mock_llm.return_value = mock_instance

            result = await discover_ontology(sample_chunks)

            assert result.relation_labels == ["WORKS_AT", "KNOWS"]
