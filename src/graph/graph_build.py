import asyncio
from typing import List
from llama_index.core import Document, PropertyGraphIndex, Settings
from llama_index.llms.openai_like import OpenAILike
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore
from llama_index.core.indices.property_graph import SchemaLLMPathExtractor

from src.graph.config_graph import GraphConfig
from src.graph.models_graph import GraphInputDocument, LocalOntology


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
            # Public labels for extractor contract 
            entity_labels = ontology.entity_labels
            relation_labels = ontology.relation_labels
            
            # Used to extract structured knowledge from unstructured text based on a predefined, strict schema. We use this extractor when building Knowledge Graphs (KGs) that require high accuracy, consistency, and alignment with a domain-specific ontology.This extractor restricts the LLM from creating arbitrary or hallucinated relationship types
            extractor = SchemaLLMPathExtractor(
                llm=self.llm,
                possible_entities=entity_labels,
                possible_relations=relation_labels,
                strict=False, 
            )

            # Keep full ontology schema on each chunk metadata for downstream processing
            ontology_payload = ontology.model_dump()

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
            if hasattr(PropertyGraphIndex, "abuild_from_documents"):
                index = await PropertyGraphIndex.abuild_from_documents(
                    llama_docs,
                    property_graph_store=self.graph_store,
                    kg_extractors=[extractor],
                    show_progress=True,
                )
            else:
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
            print(f"Error during graph extraction: {e}")
            return 0