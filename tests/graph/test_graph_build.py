"""Tests for graph extraction module."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.graph.models_graph import ProcessedChunk, LocalOntology, OntologyMetadata


# Mock heavy llama_index imports before importing graph_build
@pytest.fixture(autouse=True)
def mock_llama_index():
    """Mock all llama_index imports at fixture level."""
    with patch.dict('sys.modules', {
        'llama_index.core': MagicMock(),
        'llama_index.llms': MagicMock(),
        'llama_index.llms.openai_like': MagicMock(),
        'llama_index.embeddings': MagicMock(),
        'llama_index.embeddings.ollama': MagicMock(),
        'llama_index.graph_stores': MagicMock(),
        'llama_index.graph_stores.neo4j': MagicMock(),
        'llama_index.core.node_parser': MagicMock(),
        'llama_index.core.node_parser.text_splitter': MagicMock(),
        'llama_index.core.indices': MagicMock(),
        'llama_index.core.indices.property_graph': MagicMock(),
        'llama_index.core.settings': MagicMock(),
    }):
        yield


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


@pytest.fixture
def sample_ontology():
    """Create a sample LocalOntology for testing."""
    return LocalOntology(
        metadata=OntologyMetadata(ontology_id="test-ontology"),
        entity_types=[],
        relation_types=[],
    )


class TestExtractGraphFunction:
    """Tests for extract_graph function."""

    def test_returns_document_count(self, sample_chunks, sample_ontology):
        """Verify extract_graph returns the number of documents processed."""
        # Import here after mocks are in place
        from src.graph.graph_build import GraphExtractionStage, extract_graph

        with patch.object(GraphExtractionStage, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = len(sample_chunks)
            result = extract_graph(sample_chunks, sample_ontology)

            assert result == len(sample_chunks)
            mock_run.assert_called_once()

    def test_uses_ontology_schema(self, sample_chunks, sample_ontology):
        """Verify extraction uses ontology schema through the stage."""
        from src.graph.graph_build import GraphExtractionStage, extract_graph

        with patch.object(GraphExtractionStage, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = len(sample_chunks)
            extract_graph(sample_chunks, sample_ontology)

            # Verify ontology was passed to the stage
            call_args = mock_run.call_args
            assert call_args[0][2] == sample_ontology  # Third positional arg is ontology

    def test_accepts_custom_dataset_id(self, sample_chunks, sample_ontology):
        """Verify custom dataset_id is used when provided."""
        from src.graph.graph_build import extract_graph
        from src.graph.graph_build import GraphExtractionStage

        custom_id = "my-custom-dataset-123"

        with patch.object(GraphExtractionStage, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = len(sample_chunks)
            extract_graph(sample_chunks, sample_ontology, dataset_id=custom_id)

            call_args = mock_run.call_args
            assert call_args[0][0] == custom_id

    def test_generates_dataset_id_when_not_provided(self, sample_chunks, sample_ontology):
        """Verify dataset_id is auto-generated when not provided."""
        from src.graph.graph_build import extract_graph, GraphExtractionStage

        with patch.object(GraphExtractionStage, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = len(sample_chunks)
            extract_graph(sample_chunks, sample_ontology)

            call_args = mock_run.call_args
            dataset_id = call_args[0][0]
            # Should be a valid UUID string
            assert len(dataset_id) == 36  # UUID format


class TestGraphExtractionStage:
    """Tests for GraphExtractionStage class."""

    def test_initialization(self):
        """Verify stage initializes with config."""
        from src.graph.graph_build import GraphExtractionStage
        from src.graph.config_graph import GraphConfig

        with patch('src.graph.graph_build.OpenAILike'), \
             patch('src.graph.graph_build.OllamaEmbedding'), \
             patch('src.graph.graph_build.Neo4jPropertyGraphStore'), \
             patch('src.graph.graph_build.SentenceSplitter'):
            config = GraphConfig()
            stage = GraphExtractionStage(config)

            assert stage.config == config
            assert stage.llm is not None
            assert stage.embed_model is not None
            assert stage.graph_store is not None
            assert stage.splitter is not None

    @pytest.mark.asyncio
    async def test_run_returns_document_count(self, sample_chunks, sample_ontology):
        """Verify run method returns document count."""
        from src.graph.graph_build import GraphExtractionStage
        from src.graph.config_graph import GraphConfig

        with patch.object(GraphExtractionStage, "_run_async", new_callable=AsyncMock) as mock_async:
            mock_async.return_value = len(sample_chunks)

            config = GraphConfig()
            stage = GraphExtractionStage(config)
            result = await stage.run("test-dataset", sample_chunks, sample_ontology)

            assert result == len(sample_chunks)

    @pytest.mark.asyncio
    async def test_run_handles_errors(self, sample_chunks, sample_ontology):
        """Verify run propagates errors with context."""
        from src.graph.graph_build import GraphExtractionStage
        from src.graph.config_graph import GraphConfig

        with patch.object(GraphExtractionStage, "_run_async", new_callable=AsyncMock) as mock_async:
            mock_async.side_effect = RuntimeError("Extraction failed")

            config = GraphConfig()
            stage = GraphExtractionStage(config)

            with pytest.raises(RuntimeError, match="Extraction failed"):
                await stage.run("test-dataset", sample_chunks, sample_ontology)
