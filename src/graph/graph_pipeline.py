from typing import List, Dict, Any
from .config_graph import GraphConfig
from .models_graph import GraphInputDocument
from .ontology import OntologyDiscoveryStage
from .graph_build import GraphExtractionStage
from .normalization import GraphNormalizationStage


class UniversalGraphPipeline:
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

            chunk_count = self.extraction.run(
                dataset_id=dataset_id,
                documents=documents,
                ontology=ontology,
            )

            await self.normalization.run(dataset_id=dataset_id)

            return {
                "dataset_id": dataset_id,
                "docs": len(documents),
                "chunks": chunk_count,
                "discovered_entity_types": ontology.entity_types,
                "discovered_relation_types": ontology.relation_types,
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