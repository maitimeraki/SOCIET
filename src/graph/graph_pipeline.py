from typing import List, Dict, Any
from .config_graph import GraphConfig
from .models_graph import GraphInputDocument
from .ontology import OntologyDiscoveryStage
from .graph_build import GraphExtractionStage
from .normalization import GraphNormalizationStage


class UniversalGraphPipeline:
    """End-to-end pipeline for graph construction from unstructured documents. This class orchestrates the entire process, from discovering the ontology schema to extracting entities and relationships, and finally normalizing the graph data. It provides a single interface for users to input raw documents and receive a structured graph representation in return. The pipeline is designed to be modular, allowing for easy customization or extension of individual stages as needed."""
    def __init__(self, config: GraphConfig | None = None):
        self.config = config or GraphConfig()
        self.discovery = OntologyDiscoveryStage(
            model=self.config.discovery_model,
            temperature=self.config.temperature,
        )
        self.extraction = GraphExtractionStage(self.config)
        self.normalization = GraphNormalizationStage(self.config)

    async def run(self, dataset_id: str, documents: List[GraphInputDocument]) -> Dict[str, Any]:
        try:
            ontology = await self.discovery.run(
                documents=documents,
                sample_size=self.config.discovery_sample_size,
            )

            chunk_count = await self.extraction.run(
                dataset_id=dataset_id,
                documents=documents,
                ontology=ontology,
            )

            await self.normalization.run(dataset_id=dataset_id)

            # Public response only shows names
            public_view = ontology.to_public_view()

            return {
                "dataset_id": dataset_id,
                "docs": len(documents),
                "chunks": chunk_count,
                "discovered_entity_types": public_view.entity_types,
                "discovered_relation_types": public_view.relation_types,
                "ontology_id": ontology.metadata.ontology_id,
            }
        except Exception as e:
            print(f"Error in UniversalGraphPipeline: {e}")
            return {
                "dataset_id": dataset_id,
                "docs": len(documents),
                "chunks": 0,
                "discovered_entity_types": [],
                "discovered_relation_types": [],
                "error": str(e),
            }