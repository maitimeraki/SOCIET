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

    def test_schema_refresh_runs_once_per_store(self, monkeypatch):
        """The stage's store refreshes its schema at most once per instance."""
        import src.graph.graph_build as gb
        from src.graph.config_graph import GraphConfig

        class _Probe:
            def __init__(self, **kwargs):
                self.refreshes = 0

            def refresh_schema(self, **kwargs):
                self.refreshes += 1

        monkeypatch.setattr(gb, "Neo4jPropertyGraphStore", _Probe)
        stage = gb.GraphExtractionStage(GraphConfig())
        store = stage.graph_store
        assert isinstance(store, _Probe)
        store.refresh_schema()
        store.refresh_schema()
        store.refresh_schema()
        assert store.refreshes == 1

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


class TestStageConfigWiring:
    """Stage credentials come from central config, never literals."""

    def test_nim_credentials_come_from_config(self, monkeypatch):
        """OpenAILike receives the NIM key/base from LLMConfig (env-backed)."""
        from src.graph.config_graph import GraphConfig
        from src.graph.graph_build import GraphExtractionStage
        from src.llm.config_llm import LLMConfig

        monkeypatch.setattr(LLMConfig, "nvidia_nim_api_key", "sentinel-key")
        monkeypatch.setattr(LLMConfig, "nvidia_nim_base_url", "http://sentinel-base/v1")

        with patch('src.graph.graph_build.OpenAILike') as mock_llm, \
             patch('src.graph.graph_build.OllamaEmbedding'), \
             patch('src.graph.graph_build.Neo4jPropertyGraphStore'), \
             patch('src.graph.graph_build.SentenceSplitter'):
            GraphExtractionStage(GraphConfig())

            assert mock_llm.call_args.kwargs["api_key"] == "sentinel-key"
            assert mock_llm.call_args.kwargs["api_base"] == "http://sentinel-base/v1"

    def test_discovery_model_defaults_to_analysis_tier(self):
        """GraphConfig discovery default is the central analysis-tier model."""
        from src.graph.config_graph import GraphConfig
        from src.llm.config_llm import LLMConfig

        assert GraphConfig().discovery_model == LLMConfig.analysis_model

    def test_extraction_model_defaults_to_analysis_tier(self):
        """GraphConfig extraction default is the central analysis-tier model."""
        from src.graph.config_graph import GraphConfig
        from src.llm.config_llm import LLMConfig

        assert GraphConfig().extraction_model == LLMConfig.analysis_model


class TestNetworkBounds:
    """Every network client the stage builds carries an explicit bound."""

    def test_extraction_timeout_defaults_to_300(self):
        """GraphConfig carries the extraction timeout knob, default 300 s."""
        from src.graph.config_graph import GraphConfig

        assert GraphConfig().extraction_timeout_seconds == 300

    def test_extraction_llm_timeout_comes_from_config(self):
        """OpenAILike receives the configured timeout, not a library default."""
        from src.graph.config_graph import GraphConfig
        from src.graph.graph_build import GraphExtractionStage

        with patch('src.graph.graph_build.OpenAILike') as mock_llm, \
             patch('src.graph.graph_build.OllamaEmbedding'), \
             patch('src.graph.graph_build.Neo4jPropertyGraphStore'), \
             patch('src.graph.graph_build.SentenceSplitter'):
            GraphExtractionStage(GraphConfig(extraction_timeout_seconds=123))

            assert mock_llm.call_args.kwargs["timeout"] == 123

    def test_extraction_llm_caps_retries(self):
        """max_retries=1 — a hung attempt must not stack retries on top of the timeout."""
        from src.graph.config_graph import GraphConfig
        from src.graph.graph_build import GraphExtractionStage

        with patch('src.graph.graph_build.OpenAILike') as mock_llm, \
             patch('src.graph.graph_build.OllamaEmbedding'), \
             patch('src.graph.graph_build.Neo4jPropertyGraphStore'), \
             patch('src.graph.graph_build.SentenceSplitter'):
            GraphExtractionStage(GraphConfig())

            assert mock_llm.call_args.kwargs["max_retries"] == 1

    def test_embed_model_is_bounded_and_env_addressed(self, monkeypatch):
        """OllamaEmbedding gets LLMConfig's Ollama base URL plus a request timeout."""
        from src.graph.config_graph import GraphConfig
        from src.graph.graph_build import GraphExtractionStage
        from src.llm.config_llm import LLMConfig

        monkeypatch.setattr(LLMConfig, "ollama_base_url", "http://sentinel-ollama:1234")

        with patch('src.graph.graph_build.OpenAILike'), \
             patch('src.graph.graph_build.OllamaEmbedding') as mock_embed, \
             patch('src.graph.graph_build.Neo4jPropertyGraphStore'), \
             patch('src.graph.graph_build.SentenceSplitter'):
            GraphExtractionStage(GraphConfig())

            kwargs = mock_embed.call_args.kwargs
            assert kwargs["base_url"] == "http://sentinel-ollama:1234"
            assert kwargs["client_kwargs"]["timeout"] == 60

    @pytest.mark.asyncio
    async def test_extractors_pin_num_workers_to_one(self, sample_chunks, sample_ontology):
        """Sync mode still fans out per document (run_jobs semaphore = num_workers).

        One extraction call now carries a whole document's chunks, so the outer
        document semaphore (ontology_max_concurrency) must be the only
        concurrency lever: aggregate in-flight calls = semaphore × num_workers.
        """
        import sys

        from src.graph.config_graph import GraphConfig
        from src.graph.graph_build import GraphExtractionStage

        with patch('src.graph.graph_build.OpenAILike'), \
             patch('src.graph.graph_build.OllamaEmbedding'), \
             patch('src.graph.graph_build.Neo4jPropertyGraphStore'), \
             patch('src.graph.graph_build.SentenceSplitter'):
            stage = GraphExtractionStage(GraphConfig(ontology_max_concurrency=8))

        await stage.run("test-dataset", sample_chunks, sample_ontology)

        property_graph = sys.modules['llama_index.core.indices.property_graph']
        for extractor in (
            property_graph.SimpleLLMPathExtractor,
            property_graph.DynamicLLMPathExtractor,
        ):
            assert extractor.call_args.kwargs["num_workers"] == 1


class TestSingleChunkingOwner:
    """`split_text_sentences` already split the input — extraction must not split again."""

    @pytest.mark.asyncio
    async def test_no_resplit_documents_reach_extraction_unchunked(self, sample_ontology):
        """The transformation chain that actually runs must not re-split documents.

        Asserts the *effective* behaviour, not the literal argument: the stub
        applies the same falsy fallback `BaseIndex.from_documents` does
        (`transformations or Settings.transformations`), so an empty list would
        resolve to the stage's splitter and be caught here.
        """
        import sys

        from src.graph.config_graph import GraphConfig
        from src.graph.graph_build import GraphExtractionStage

        chunks = [
            ProcessedChunk(
                chunk_id=f"chunk-{i}",
                parent_doc_id="doc-1",
                chunk_index=i,
                content_hash=f"hash{i}",
                content=f"Pre-split chunk body number {i}.",
                summary_context="Software architecture overview",
                breadcrumb="docs/architecture",
                header_level=1,
                domain_tags=["software"],
                expertise_level="Technical",
                metadata={"title": "System Architecture"},
            )
            for i in range(3)
        ]

        captured = {}

        def _fake_from_documents(documents, **kwargs):
            # Mirror llama-index: BaseIndex.from_documents resolves
            # `transformations = transformations or Settings.transformations`.
            resolved = kwargs["transformations"] or core.Settings.transformations
            captured["transformations"] = resolved
            nodes = list(documents)
            for transform in resolved:
                nodes = list(transform(nodes))
            index = MagicMock()
            # Derive the store from what actually survived transformation, so the
            # count reflects behaviour rather than a fabricated size.
            index.docstore.docs = {f"node-{i}": n for i, n in enumerate(nodes)}
            return index

        with patch('src.graph.graph_build.OpenAILike'), \
             patch('src.graph.graph_build.OllamaEmbedding'), \
             patch('src.graph.graph_build.Neo4jPropertyGraphStore'), \
             patch('src.graph.graph_build.SentenceSplitter'):
            stage = GraphExtractionStage(GraphConfig())

        core = sys.modules['llama_index.core']
        # Production pins Settings.node_parser = self.splitter; the real
        # Settings.transformations returns [Settings.node_parser]. Model it so
        # the fallback resolves to the splitter exactly as it does live.
        core.Settings.transformations = [stage.splitter]
        core.PropertyGraphIndex.from_documents.side_effect = _fake_from_documents

        count = await stage.run("test-dataset", chunks, sample_ontology)

        resolved = captured["transformations"]
        assert resolved is not core.Settings.transformations  # fallback not taken
        assert stage.splitter not in resolved  # no SentenceSplitter in the chain
        assert count == len(chunks)
