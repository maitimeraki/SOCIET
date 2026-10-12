"""Tests for graph extraction module."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.graph.models_graph import ProcessedChunk, LocalOntology, OntologyMetadata


# Mock heavy llama_index imports before importing graph_build
@pytest.fixture(autouse=True)
def mock_llama_index():
    """Mock all llama_index imports at fixture level.

    `patch.dict` reaches only modules that have NOT been imported yet: any module
    importing `graph_build` earlier (e.g. `graph_snapshot`, which reuses its
    `_public_props`) binds the REAL llama-index classes into graph_build's
    namespace before this patch runs. Re-point graph_build's own module-level
    names too, so the stage never dials a real Neo4j whatever the import order.
    """
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
        # Task 7: `_proposed_labels` / `_delta_payload` read these keys lazily.
        'llama_index.core.graph_stores': MagicMock(),
        'llama_index.core.graph_stores.types': MagicMock(),
    }):
        import src.graph.graph_build as gb
        with patch.object(gb, "OpenAILike", MagicMock()), \
             patch.object(gb, "OllamaEmbedding", MagicMock()), \
             patch.object(gb, "Neo4jPropertyGraphStore", MagicMock()), \
             patch.object(gb, "SentenceSplitter", MagicMock()):
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
        assert property_graph.DynamicLLMPathExtractor.call_args.kwargs["num_workers"] == 1


class TestSingleChunkingOwner:
    """`split_text_sentences` already split the input — extraction must not split again."""

    @pytest.mark.asyncio
    async def test_documents_reach_extraction_unchunked_once(self, sample_ontology):
        """Each pre-split chunk becomes exactly one extracted node — no re-split.

        Task 7 replaced the single `from_documents` build with a per-chunk
        sliding window. The single-chunking-owner invariant now means: the
        stage wraps each ProcessedChunk in one Document and hands exactly one
        node to the extractors per chunk (1:1), never re-splitting — and the
        empty index it builds carries a truthy no-op `kg_extractor`, so the
        index's own insert path cannot re-run the default extractors either.
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

        seen = []

        def _recording_extractor(nodes):
            seen.extend(nodes)
            return nodes

        with patch('src.graph.graph_build.OpenAILike'), \
             patch('src.graph.graph_build.OllamaEmbedding'), \
             patch('src.graph.graph_build.Neo4jPropertyGraphStore'), \
             patch('src.graph.graph_build.SentenceSplitter'):
            stage = GraphExtractionStage(GraphConfig())

        core = sys.modules['llama_index.core']
        # Production pins Settings.node_parser = self.splitter; the splitter must
        # never be reached by the per-chunk path.
        core.Settings.transformations = [stage.splitter]
        index = core.PropertyGraphIndex.return_value
        index.docstore.docs = {f"node-{i}": MagicMock() for i in range(len(chunks))}

        with patch.object(GraphExtractionStage, "_build_extractors", return_value=[_recording_extractor]):
            count = await stage.run("test-dataset", chunks, sample_ontology)

        assert count == len(chunks)          # one docstore node per chunk
        assert len(seen) == len(chunks)      # one extraction pass, 1:1 — no re-split

        # the empty index is built with a truthy no-op extractor, so its own
        # `_insert_nodes` only performs the store writes (never re-extracts)
        built = core.PropertyGraphIndex.call_args.kwargs
        assert type(built["kg_extractors"][0]).__name__ == "_NoOpSplit"


class TestExtractionPromptForbidsValueNodes:
    """Task 5: the extractor prompt forbids value entities; the triple-only
    extractor is retired.

    These tests read the extractor class handles OUT of the mocked
    `llama_index.core.indices.property_graph` module — that is the very module
    `_build_extractors` imports from, so the assertions exercise the real
    construction path rather than a second, disconnected mock.
    """

    def _stage(self):
        from src.graph.config_graph import GraphConfig
        from src.graph.graph_build import GraphExtractionStage

        with patch('src.graph.graph_build.OpenAILike'), \
             patch('src.graph.graph_build.OllamaEmbedding'), \
             patch('src.graph.graph_build.Neo4jPropertyGraphStore'), \
             patch('src.graph.graph_build.SentenceSplitter'):
            return GraphExtractionStage(GraphConfig())

    def test_no_simple_extractor_and_prompt_forbids_value_nodes(self, sample_ontology):
        import sys

        stage = self._stage()
        property_graph = sys.modules['llama_index.core.indices.property_graph']
        property_graph.reset_mock()

        extractors = stage._build_extractors(sample_ontology)

        assert property_graph.SimpleLLMPathExtractor.call_count == 0   # triple-only extractor retired
        assert len(extractors) == 2                                    # dynamic + implicit
        prompt = property_graph.DynamicLLMPathExtractor.call_args.kwargs["extract_prompt"]
        assert "never" in prompt.lower() and "propert" in prompt.lower()

    def test_extraction_prompt_braces_match_extractor_kwargs(self):
        """Every `{...}` the custom prompt references is one the extractor supplies.

        `DynamicLLMPathExtractor` formats its prompt with exactly
        `text`, `max_knowledge_triplets`, `allowed_entity_types`,
        `allowed_relation_types`, `allowed_entity_properties` and
        `allowed_relation_properties`; an unknown brace raises `KeyError` at
        extraction time, so the used set must be a subset of the supplied set.
        """
        import string

        from src.graph.graph_build import _EXTRACTION_PROMPT

        supplied = {
            "text",
            "max_knowledge_triplets",
            "allowed_entity_types",
            "allowed_relation_types",
            "allowed_entity_properties",
            "allowed_relation_properties",
        }
        used = {
            name
            for _, name, _, _ in string.Formatter().parse(_EXTRACTION_PROMPT)
            if name
        }
        assert used <= supplied
        _EXTRACTION_PROMPT.format(**{name: "x" for name in supplied})   # renders, no KeyError


class TestLiteralRouting:
    """Task 6: a literal node becomes a typed property slot, then disappears."""

    def _stage(self):
        from src.graph.config_graph import GraphConfig
        from src.graph.graph_build import GraphExtractionStage

        with patch('src.graph.graph_build.OpenAILike'), \
             patch('src.graph.graph_build.OllamaEmbedding'), \
             patch('src.graph.graph_build.Neo4jPropertyGraphStore'), \
             patch('src.graph.graph_build.SentenceSplitter'):
            return GraphExtractionStage(GraphConfig())

    @staticmethod
    def _pin_kg_keys():
        """`_extract_chunk` reads KG_NODES_KEY/KG_RELATIONS_KEY from the mocked
        `llama_index.core.graph_stores.types`; pin them to their real string
        values so this test's metadata bag is the one the code reads."""
        import sys

        types = sys.modules['llama_index.core.graph_stores.types']
        types.KG_NODES_KEY = "nodes"
        types.KG_RELATIONS_KEY = "relations"

    def test_extract_chunk_routes_literals_onto_real_to_real_relation(self):
        """§13.2: a leaked value lands on the SURVIVING real→real edge's declared
        slot, and that edge — not the literal's own dangling edge — stays in the
        delta."""
        from unittest.mock import MagicMock

        from src.graph.models_graph import (
            LocalOntology,
            OntologyMetadata,
            PropertyDefinition,
            RelationTypeDefinition,
        )

        self._pin_kg_keys()
        stage = self._stage()

        amazon = MagicMock(); amazon.id = "e2"; amazon.name = "Amazon"; amazon.label = "Company"; amazon.properties = {}
        whole = MagicMock(); whole.id = "e3"; whole.name = "WholeFoods"; whole.label = "Company"; whole.properties = {}
        money = MagicMock(); money.id = "e1"; money.name = "$2.5 billion"; money.label = "Money"
        acquired = MagicMock(); acquired.source_id = "e2"; acquired.target_id = "e3"; acquired.label = "ACQUIRED"; acquired.properties = {}
        price_edge = MagicMock(); price_edge.source_id = "e3"; price_edge.target_id = "e1"; price_edge.label = "PRICE"; price_edge.properties = {}

        def _extractor(nodes):
            nodes[0].metadata = {"nodes": [amazon, whole, money], "relations": [acquired, price_edge]}
            return nodes

        ontology = LocalOntology(
            metadata=OntologyMetadata(ontology_id="test-ontology"),
            relation_types=[
                RelationTypeDefinition(
                    type_name="ACQUIRED",
                    properties=[PropertyDefinition(name="price", value_type="money")],
                )
            ],
        )

        doc = MagicMock(); doc.metadata = {}
        _, ent_labels, _, delta_nodes, delta_edges = stage._extract_chunk(
            doc, [_extractor], ontology.relation_types
        )

        assert [n["label"] for n in delta_nodes] == ["Amazon", "WholeFoods"]   # literal node gone
        assert "Money" not in ent_labels
        assert [(e["source"], e["target"]) for e in delta_edges] == [("e2", "e3")]   # ACQUIRED survives
        assert acquired.properties["price"] == {"amount": 2.5e9, "currency": "USD"}
        assert "price" not in price_edge.properties   # value not stranded on the dropped edge

    def test_two_same_kind_literals_route_to_their_own_relation(self):
        """Two money literals must not collide on one real→real edge.

        A deal price adjacent to WholeFoods lands on ACQUIRED; a revenue
        adjacent to RevenueCo2 lands on HAS_REVENUE — neither overwrites the
        other (before the fix, the first-match scan sent both to ACQUIRED).
        """
        from unittest.mock import MagicMock

        from src.graph.models_graph import (
            LocalOntology,
            OntologyMetadata,
            PropertyDefinition,
            RelationTypeDefinition,
        )

        self._pin_kg_keys()
        stage = self._stage()

        amazon = MagicMock(); amazon.id = "e2"; amazon.name = "Amazon"; amazon.label = "Company"; amazon.properties = {}
        whole = MagicMock(); whole.id = "e3"; whole.name = "WholeFoods"; whole.label = "Company"; whole.properties = {}
        revco = MagicMock(); revco.id = "e5"; revco.name = "RevenueCo"; revco.label = "Company"; revco.properties = {}
        revco2 = MagicMock(); revco2.id = "e6"; revco2.name = "RevenueCo2"; revco2.label = "Company"; revco2.properties = {}
        deal = MagicMock(); deal.id = "e1"; deal.name = "$2.5 billion"; deal.label = "Money"
        revenue = MagicMock(); revenue.id = "e4"; revenue.name = "$391 billion"; revenue.label = "Money"
        acquired = MagicMock(); acquired.source_id = "e2"; acquired.target_id = "e3"; acquired.label = "ACQUIRED"; acquired.properties = {}
        has_revenue = MagicMock(); has_revenue.source_id = "e5"; has_revenue.target_id = "e6"; has_revenue.label = "HAS_REVENUE"; has_revenue.properties = {}
        price_edge = MagicMock(); price_edge.source_id = "e3"; price_edge.target_id = "e1"; price_edge.label = "PRICE"; price_edge.properties = {}
        rev_edge = MagicMock(); rev_edge.source_id = "e6"; rev_edge.target_id = "e4"; rev_edge.label = "REV"; rev_edge.properties = {}

        def _extractor(nodes):
            nodes[0].metadata = {
                "nodes": [amazon, whole, revco, revco2, deal, revenue],
                "relations": [acquired, has_revenue, price_edge, rev_edge],
            }
            return nodes

        ontology = LocalOntology(
            metadata=OntologyMetadata(ontology_id="test-ontology"),
            relation_types=[
                RelationTypeDefinition(
                    type_name="ACQUIRED",
                    properties=[PropertyDefinition(name="price", value_type="money")],
                ),
                RelationTypeDefinition(
                    type_name="HAS_REVENUE",
                    properties=[PropertyDefinition(name="amount", value_type="money")],
                ),
            ],
        )

        doc = MagicMock(); doc.metadata = {}
        stage._extract_chunk(doc, [_extractor], ontology.relation_types)

        assert acquired.properties["price"] == {"amount": 2.5e9, "currency": "USD"}
        assert has_revenue.properties["amount"] == {"amount": 391e9, "currency": "USD"}

    def test_extract_chunk_routes_literals_onto_surviving_entity(self):
        """The literal's only real neighbour takes the value under the relation's
        lowercased label — the value survives the drop (§13.1)."""
        from unittest.mock import MagicMock

        self._pin_kg_keys()
        stage = self._stage()

        amazon = MagicMock(); amazon.id = "e2"; amazon.name = "Amazon"; amazon.label = "Company"; amazon.properties = {}
        money = MagicMock(); money.id = "e1"; money.name = "$2.5 billion"; money.label = "Money"
        rel = MagicMock(); rel.source_id = "e2"; rel.target_id = "e1"; rel.label = "ACQUIRED"; rel.properties = {}

        def _extractor(nodes):
            nodes[0].metadata = {"nodes": [amazon, money], "relations": [rel]}
            return nodes

        doc = MagicMock(); doc.metadata = {}
        _, ent_labels, _, delta_nodes, delta_edges = stage._extract_chunk(doc, [_extractor])

        assert [n["label"] for n in delta_nodes] == ["Amazon"]     # literal node gone
        assert "Money" not in ent_labels
        assert delta_edges == []                                   # dangling edge removed
        assert amazon.properties["acquired"] == {"amount": 2.5e9, "currency": "USD"}

    def test_literal_routes_into_declared_entity_slot(self):
        """With a declared matching slot, the entity takes that slot's name."""
        from unittest.mock import MagicMock

        from src.graph.models_graph import (
            LocalOntology,
            OntologyMetadata,
            PropertyDefinition,
            RelationTypeDefinition,
        )

        self._pin_kg_keys()
        stage = self._stage()

        amazon = MagicMock(); amazon.id = "e2"; amazon.name = "Amazon"; amazon.label = "Company"; amazon.properties = {}
        money = MagicMock(); money.id = "e1"; money.name = "$2.5 billion"; money.label = "Money"
        rel = MagicMock(); rel.source_id = "e2"; rel.target_id = "e1"; rel.label = "ACQUIRED"; rel.properties = {}

        def _extractor(nodes):
            nodes[0].metadata = {"nodes": [amazon, money], "relations": [rel]}
            return nodes

        ontology = LocalOntology(
            metadata=OntologyMetadata(ontology_id="test-ontology"),
            relation_types=[
                RelationTypeDefinition(
                    type_name="ACQUIRED",
                    properties=[PropertyDefinition(name="price", value_type="money")],
                )
            ],
        )

        doc = MagicMock(); doc.metadata = {}
        stage._extract_chunk(doc, [_extractor], ontology.relation_types)

        assert amazon.properties["price"] == {"amount": 2.5e9, "currency": "USD"}

    def test_extract_chunk_drops_relations_between_two_literals(self):
        from unittest.mock import MagicMock

        self._pin_kg_keys()
        stage = self._stage()

        rel = MagicMock()
        rel.source_id = "e1"; rel.target_id = "e2"; rel.label = "ON"; rel.properties = {}

        def _extractor(nodes):
            year = MagicMock(); year.id = "e1"; year.name = "2018"; year.label = "Date"
            share = MagicMock(); share.id = "e2"; share.name = "40%"; share.label = "Percentage"
            nodes[0].metadata = {"nodes": [year, share], "relations": [rel]}
            return nodes

        doc = MagicMock(); doc.metadata = {}
        _, ent_labels, _, delta_nodes, delta_edges = stage._extract_chunk(doc, [_extractor])

        assert delta_nodes == []
        assert ent_labels == []
        assert delta_edges == []


class TestDeltaPayloadProperties:
    """Task 7: a delta carries the extracted facts, not just the node skeleton.

    The autouse fixture serves MagicMock sentinels for the KG metadata keys, so
    pin them to their real string values — the same seam `TestLiteralRouting`
    uses — so this exercises the dict lookup the live path performs.
    """

    @staticmethod
    def _pin_kg_keys():
        import sys

        types = sys.modules['llama_index.core.graph_stores.types']
        types.KG_NODES_KEY = "nodes"
        types.KG_RELATIONS_KEY = "relations"

    def test_delta_payload_carries_properties(self):
        from unittest.mock import MagicMock

        from src.graph.graph_build import _delta_payload

        self._pin_kg_keys()
        item = MagicMock(); item.id = "e1"; item.name = "Amazon"; item.label = "Company"
        item.properties = {"revenue": "$391B", "chunk_id": "c1"}   # chunk_id is lineage, not a fact
        node = MagicMock(); node.metadata = {"nodes": [item], "relations": []}

        nodes, _ = _delta_payload([node])

        assert nodes[0]["properties"] == {"revenue": "$391B"}
        assert nodes[0]["kind"] == "Company"

    def test_delta_payload_carries_edge_properties(self):
        from unittest.mock import MagicMock

        from src.graph.graph_build import _delta_payload

        self._pin_kg_keys()
        rel = MagicMock(); rel.source_id = "e2"; rel.target_id = "e3"; rel.label = "ACQUIRED"
        rel.properties = {"price": "$2.5B", "document_anchor": "x"}
        node = MagicMock(); node.metadata = {"nodes": [], "relations": [rel]}

        _, edges = _delta_payload([node])

        assert edges[0]["properties"] == {"price": "$2.5B"}
