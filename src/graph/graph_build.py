from typing import List
from llama_index.core import Document, PropertyGraphIndex, Settings
from llama_index.llms.openai import OpenAI
from llama_index.llms.openai_like import OpenAILike
from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore
from llama_index.core.indices.property_graph import SchemaLLMPathExtractor

from src.graph.config_graph import GraphConfig
from src.graph.models_graph import GraphInputDocument, LocalOntology


class GraphExtractionStage:
    def __init__(self, config: GraphConfig):
        self.config = config
        self.llm = OpenAILike(
            model=config.extraction_model,
            api_base="http://localhost:11434/v1",
            api_key="ollama",
            timeout=120,  # ADD THIS
            max_retries=3,  # ADD THIS
    # If using local models, they often need longer timeouts
        )
        print(f"Initialized GraphExtractionStage with model: {config}")
        self.graph_store = Neo4jPropertyGraphStore(
            username=config.neo4j_username,
            password=config.neo4j_password,
            url=config.neo4j_uri,
            database=config.neo4j_database,
        )

    def run(
        self,
        dataset_id: str,
        documents: List[GraphInputDocument],
        ontology: LocalOntology,
    ) -> int:
        Settings.llm = self.llm
        try:

            extractor = SchemaLLMPathExtractor(
                llm=self.llm,
                possible_entities=ontology.entity_types,
                possible_relations=ontology.relation_types,
                strict=False,
            )

            llama_docs = []
            for d in documents:
                md = dict(d.metadata)
                md["dataset_id"] = dataset_id
                md["document_id"] = d.document_id
                if d.title:
                    md["title"] = d.title
                llama_docs.append(Document(text=d.text, metadata=md))

            index = PropertyGraphIndex.from_documents(
                llama_docs,
                property_graph_store=self.graph_store,
                kg_extractors=[extractor],
                show_progress=True,
            )

            return len(index.docstore.docs)
        except Exception as e:
            print(f"Error during graph extraction: {e}")
            return 0