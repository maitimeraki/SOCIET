import asyncio
import logging
import sys
from typing import List, Literal
from llama_index.core import Document, PropertyGraphIndex, Settings
from llama_index.llms.openai_like import OpenAILike
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore
from llama_index.core.indices.property_graph import SchemaLLMPathExtractor
from src.logging.setup_logging import setup_logging
from src.graph.config_graph import GraphConfig
from src.graph.models_graph import GraphInputDocument, LocalOntology


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
class GraphExtractionStage:
    """Extracts entities and relationships from documents using LLMs and stores them in a Neo4j graph database.
    This stage is responsible for taking raw text documents, applying the defined ontology schema to extract structured information."""
    def __init__(self, config: GraphConfig):
        self.config = config
        self.llm = OpenAILike(
            model=config.extraction_model,
            api_base="http://localhost:11434/v1",
            api_key="ollama",
            timeout=120,
            max_retries=3,
        )
        # Specialized embedding model for generating vector representations of text, which can be used for semantic search, clustering, or as part of the extraction process to improve accuracy. This allows the system to capture nuanced meanings and relationships in the text that may not be explicitly defined in the ontology.
        self.embed_model = OllamaEmbedding(
            model_name="nomic-embed-text:v1.5",
            base_url="http://localhost:11434",
            ollama_additional_kwargs={"mirostat": 0},
        )
        # Neo4j graph store for persisting extracted entities and relationships. This allows for efficient querying and analysis of the constructed knowledge graph, as well as integration with other tools that support the Neo4j format.
        self.graph_store = Neo4jPropertyGraphStore(
            username=config.neo4j_username,
            password=config.neo4j_password,
            url=config.neo4j_uri,
            database=config.neo4j_database,
        )

    async def run(
        self,
        dataset_id: str,
        documents: List[GraphInputDocument],
        ontology: LocalOntology,
    ) -> int:
        Settings.llm = self.llm
        try:
            # 1. Transform basic labels into a Property-Aware Schema
            # We map each entity label to its discovered properties dynamically
            logger.info(f"Transforming ontology schema for dataset {dataset_id} into property-aware format.")
            entity_schemas = ontology.entity_labels
            relation_schemas = ontology.relation_labels
            possible_ent_props = ontology.entity_props
            possible_rel_props = ontology.relation_props
            
            # Used to extract structured knowledge from unstructured text based on a predefined, strict schema. We use this extractor when building Knowledge Graphs (KGs) that require high accuracy, consistency, and alignment with a domain-specific ontology.This extractor restricts the LLM from creating arbitrary or hallucinated relationship types
            logger.info(f"Initializing SchemaLLMPathExtractor for dataset {dataset_id} with {(entity_schemas)} entity schemas and {(relation_schemas)} relation schemas.")
            extractor = SchemaLLMPathExtractor(
                llm=self.llm,
                possible_entities=entity_schemas,
                possible_relations=relation_schemas,
                possible_entity_props=possible_ent_props,
                possible_relation_props=possible_rel_props,
                
                strict=True, # Strict ensures it doesn't hallucinate non-schema properties
            )

            # Keep full ontology schema on each chunk metadata for downstream processing
            ontology_payload = ontology.model_dump()
            logger.info(f"Prepared ontology payload for dataset {dataset_id}: {ontology_payload}")

            llama_docs = []
            for d in documents:
                md = dict(d.metadata)
                md["dataset_id"] = dataset_id
                md["document_id"] = d.document_id
                md["ontology_id"] = ontology.metadata.ontology_id
                md["ontology_schema"] = ontology_payload
                if d.title:
                    md["title"] = d.title
                llama_docs.append(Document(text=d.text, metadata=md))
            # Sophisticated indexing structure that constructs a knowledge graph from unstructured data (documents), where nodes and relationships can have properties (metadata). Unlike earlier "triple-based" knowledge graphs, this allows for much richer, semantic modeling.
            logger.info(f"Building property graph for dataset {dataset_id}")
            if hasattr(PropertyGraphIndex, "abuild_from_documents"):
                index = await PropertyGraphIndex.abuild_from_documents(
                    llama_docs,
                    property_graph_store=self.graph_store,
                    kg_extractors=[extractor],
                    show_progress=True,
                )
            else:
                logger.warning(f"PropertyGraphIndex.abuild_from_documents not found. Falling back to synchronous from_documents method for dataset {dataset_id}. This may block the event loop.")
                index = await asyncio.to_thread(
                    PropertyGraphIndex.from_documents,
                    llama_docs,
                    embed_model=self.embed_model,
                    property_graph_store=self.graph_store,
                    kg_extractors=[extractor],
                    show_progress=True,
                )

            return len(index.docstore.docs)
        except Exception as e:
            logger.error(f"Error during graph extraction: {e}")
            return 0