import asyncio
import logging
import sys
import uuid
from typing import List, Optional
from src.logging.setup_logging import setup_logging
from llama_index.core.node_parser import SentenceSplitter
from llama_index.llms.openai_like import OpenAILike
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore
from src.graph.config_graph import GraphConfig
from src.graph.models_graph import ProcessedChunk, LocalOntology


# Configure basic logging
logging.basicConfig(
    level=logging.INFO,  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)  # Output to terminal
    ]
)
logging.warning("This is a warning message. Check your configuration or code for potential issues.")
logging.basicConfig(level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s")

# Create logger instance
# logger = logging.getLogger(__name__)
logger = setup_logging()  # Ensure logging is configured with handler clearing to prevent duplication

# Document-first node model (P4-T1): a Document node per source document, created
# before extraction, and a DERIVED_FROM edge from every extracted concept to it.
# `domain_tags` accumulates and dedupes instead of overwriting: the live path
# calls the stage one chunk at a time, so repeated calls for one document must
# converge to the document-wide union.
_MERGE_DOCUMENTS = """
UNWIND $docs AS row
MERGE (d:Document {document_id: row.document_id, dataset_id: row.dataset_id})
SET d.domain_tags = coalesce(d.domain_tags, []) + [t IN row.domain_tags WHERE NOT t IN coalesce(d.domain_tags, [])]
"""

_LINK_CONCEPTS_TO_DOCUMENTS = """
UNWIND $rows AS row
MATCH (c:__Node__ {id: row.chunk_id})-[:MENTIONS]->(e:__Entity__)
MATCH (d:Document {document_id: row.document_id, dataset_id: $dataset_id})
MERGE (e)-[:DERIVED_FROM]->(d)
"""


def _document_rows(dataset_id: str, documents: List[ProcessedChunk]) -> List[dict]:
    """One row per unique `parent_doc_id`: its dataset plus the deduped,
    order-stable union of its chunks' `domain_tags`."""
    rows: dict[str, dict] = {}
    for d in documents:
        row = rows.setdefault(
            d.parent_doc_id,
            {"document_id": d.parent_doc_id, "dataset_id": dataset_id, "domain_tags": []},
        )
        for tag in d.domain_tags or []:
            if tag not in row["domain_tags"]:
                row["domain_tags"].append(tag)
    return list(rows.values())


class GraphExtractionStage:
    """Extracts entities and relationships from documents using LLMs and stores them in a Neo4j graph database.
    This stage is responsible for taking raw text documents, applying the defined ontology schema to extract structured information."""
    def __init__(self, config: GraphConfig):
        self.config = config
        self.llm = OpenAILike(
                model=self.config.extraction_model,
                api_base="http://localhost:11434/v1",
                api_key="ollama",
                temperature=0.7,
                timeout=900,
                max_retries=3,
            )
        self.embed_model = OllamaEmbedding(
            model_name="nomic-embed-text:v1.5",
            base_url="http://localhost:11434",
            ollama_additional_kwargs={"mirostat": 0},
        )
        self.graph_store = Neo4jPropertyGraphStore(
            username=self.config.neo4j_username,
            password=self.config.neo4j_password,
            url=self.config.neo4j_uri,
            database=self.config.neo4j_database,
        )
        self.splitter = SentenceSplitter(chunk_size=2048, chunk_overlap=400)
        
    async def run(
        self,
        dataset_id: str,
        documents: List[ProcessedChunk],
        ontology: LocalOntology,
    ) -> int:
        try:
            # Call the async logic directly
            return await self._run_async(dataset_id, documents, ontology)
        except Exception as e:
            logger.error(f"Error in GraphExtractionStage for dataset {dataset_id}: {e}")
            raise

    async def _run_async(
        self,
        dataset_id: str,
        documents: List[ProcessedChunk],
        ontology: LocalOntology,
    ) -> int:
        import os
        os.environ["LLAMA_INDEX_DISABLE_ASYNC_EMBEDDINGS"] = "1"
        from llama_index.core import Document, PropertyGraphIndex, Settings

        Settings.llm = self.llm
        # ✅ FIX: Disable async embeddings to prevent nested loop creation
        Settings.embed_model = self.embed_model
        Settings.node_parser = self.splitter

        logger.info(f"Transforming ontology schema for dataset {dataset_id} into property-aware format.")
        try:
            entity_schemas = ontology.entity_labels
            relation_schemas = ontology.relation_labels
            possible_ent_props = ontology.entity_props
            possible_rel_props = ontology.relation_props

            logger.info(
                f"Initializing SchemaLLMPathExtractor for dataset {dataset_id} with "
                f"{entity_schemas} entity schemas and {relation_schemas} relation schemas."
            )

            from llama_index.core.indices.property_graph import (
                SimpleLLMPathExtractor,
                DynamicLLMPathExtractor,
                ImplicitPathExtractor,
            )
            # Simple extractor - basic triple extraction without schema constraints(Simple extractor captures additional relationships the dynamic one might miss)
            simple_extractor = SimpleLLMPathExtractor(
                llm=self.llm,
                max_paths_per_chunk=10,
                num_workers=self.config.ontology_max_concurrency,
            )
            # Dynamic extractor - schema-guided but flexible(Dynamic extractor captures labeled entities/relations following your schema)
            dynamic_extractor = DynamicLLMPathExtractor(
                llm=self.llm,
                allowed_entity_types=entity_schemas,
                allowed_relation_types=relation_schemas,
                allowed_entity_props=possible_ent_props,
                allowed_relation_props=possible_rel_props,
                num_workers=self.config.ontology_max_concurrency,
            )
            # Implicit extractor - from node relationships(Implicit extractor adds structural relationships between nodes that LLMs don't generate)
            implicit_extractor = ImplicitPathExtractor()
            

            llama_docs = []
            for d in documents:
                md = dict(d.metadata)
                md["dataset_id"] = dataset_id
                # llama-index overwrites the graph `document_id` property with the
                # split node's ref_doc_id at write time (node_to_metadata_dict) —
                # `document_anchor` is the graph-level carrier of the source
                # document id, and `chunk_id` the original chunk id.
                md["document_id"] = d.parent_doc_id
                md["chunk_id"] = d.chunk_id
                md["document_anchor"] = d.parent_doc_id
                md["chunk_index"] = d.chunk_index
                md["content_hash"] = d.content_hash
                md["summary_context"] = d.summary_context
                md["domain_tags"] = d.domain_tags
                md["expertise_level"] = d.expertise_level
                md["breadcrumb"] = d.breadcrumb
                md["header_level"] = d.header_level
                md["ontology_id"] = ontology.metadata.ontology_id
                # `_create_processed_chunk` carries the filename as `source_document`;
                # without the fallback every provenance link title is "Untitled Document".
                md["title"] = md.get("title") or md.get("source_document") or "Untitled Document"
                new_doc = Document(text=d.content, metadata=md)
                
                
                new_doc.excluded_llm_metadata_keys = ["dataset_id", "ontology_id", "document_id", "chunk_id", "document_anchor", "content_hash", "chunk_index"]  # Exclude sensitive or non-informative metadata from LLM input
                new_doc.excluded_embed_metadata_keys = ["dataset_id", "ontology_id", "document_id", "chunk_id", "document_anchor", "content_hash", "chunk_index"]  # Exclude from embedding metadata as well to prevent noise in vector representations
                llama_docs.append(new_doc)

            logger.info(f"Building property graph for dataset {dataset_id}")
            
            # Since PropertyGraphIndex.from_documents can be synchronous and blocking
            # we execute it securely in a thread utilizing the CURRENT event loop's context
            def _build_index():
                # ✅ Use synchronous index building instead
                return PropertyGraphIndex.from_documents(
                    llama_docs,
                    embed_model=self.embed_model,
                    property_graph_store=self.graph_store,
                    kg_extractors=[simple_extractor, dynamic_extractor, implicit_extractor],
                    transformations=[self.splitter],
                    use_async=False,  # ← FORCE SYNC MODE if available
                    show_progress=True,
                )

            # Document-first: the Document nodes exist before extraction so the
            # DERIVED_FROM pass below has something to link to.
            await asyncio.to_thread(self._write_documents, dataset_id, documents)

            index = await asyncio.to_thread(_build_index)

            await asyncio.to_thread(self._link_concepts_to_documents, index, dataset_id)
            return len(index.docstore.docs)

        except Exception as e:
            logger.error(f"Error during graph extraction for dataset {dataset_id}: {e}")
            raise

    def _write_documents(self, dataset_id: str, documents: List[ProcessedChunk]) -> None:
        """MERGE one Document node per unique source document. Sync — called off the loop."""
        rows = _document_rows(dataset_id, documents)
        if rows:
            self.graph_store.structured_query(_MERGE_DOCUMENTS, param_map={"docs": rows})

    def _link_concepts_to_documents(self, index, dataset_id: str) -> None:
        """MERGE `(concept)-[:DERIVED_FROM]->(Document)` for every stored chunk
        that carries a `document_anchor`. Sync — called off the loop."""
        rows = []
        for node_id, node in (index.docstore.docs or {}).items():
            document_id = (getattr(node, "metadata", None) or {}).get("document_anchor")
            if document_id:
                rows.append({"chunk_id": node_id, "document_id": document_id})
        if rows:
            self.graph_store.structured_query(
                _LINK_CONCEPTS_TO_DOCUMENTS,
                param_map={"rows": rows, "dataset_id": dataset_id},
            )


def extract_graph(
    chunks: List[ProcessedChunk],
    ontology: LocalOntology,
    dataset_id: Optional[str] = None,
    config: Optional[GraphConfig] = None,
) -> int:
    """Extract entities and relationships from chunks using ontology schema.

    Args:
        chunks: List of processed document chunks to extract from.
        ontology: LocalOntology defining entity and relation types to extract.
        dataset_id: Optional dataset identifier. Auto-generated if not provided.
        config: Optional GraphConfig. Creates default if not provided.

    Returns:
        Number of documents/chunks processed.
    """
    if dataset_id is None:
        dataset_id = str(uuid.uuid4())

    if config is None:
        config = GraphConfig()

    stage = GraphExtractionStage(config)

    # Synchronous wrapper for the async run method
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is already running, create a new task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run, stage.run(dataset_id, chunks, ontology)
                )
                return future.result()
        else:
            return loop.run_until_complete(stage.run(dataset_id, chunks, ontology))
    except RuntimeError:
        # No event loop exists, create one
        return asyncio.run(stage.run(dataset_id, chunks, ontology))