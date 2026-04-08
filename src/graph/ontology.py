import sys
import json
import logging
from datetime import datetime
from typing import List, Dict, Any
from llama_index.llms.openai_like import OpenAILike
from src.utils.hydrate_ontology import hydrate_ontology
from src.graph.models_graph import (
    GraphInputDocument,
    LocalOntology,
    OntologyMetadata,
)

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)  # Output to terminal
    ]
)
logging.basicConfig(level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s")

# Create logger instance
logger = logging.getLogger(__name__)


def _strip_json_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.replace("```json", "").replace("```", "").strip()
    return t

def _structured_properties(llm_data: Dict[str, Any]) -> Dict[str, Any]:
    # This transforms the flat strings back into your strict Pydantic objects
    for ent in llm_data.get("entity_types", []):
        parsed_props = []
        for prop_str in ent.get("properties", []):
            if ":" in prop_str:
                name, desc = prop_str.split(":", 1)
                parsed_props.append({
                    "name": name.strip(),
                    "description": desc.strip()
                })
        ent["properties"] = parsed_props # Now matches your class schema
        
    for rel in llm_data.get("relation_types", []):
        parsed_props = []
        for prop_str in rel.get("properties", []):
            if ":" in prop_str:
                name, desc = prop_str.split(":", 1)
                parsed_props.append({
                    "name": name.strip(),
                    "description": desc.strip()
                })
        rel["properties"] = parsed_props # Now matches your class schema
    
    return llm_data

# def _normalize_ontology_shape(parsed: Dict[str, Any]) -> Dict[str, Any]:
#     entity_types = parsed.get("entity_types", []) # return type -> List[Dict[str, Any]]
#     relation_types = parsed.get("relation_types", []) # return type -> List[Dict[str, Any]]
#     logger.info(f"Normalizing ontology shape. Initial entity_types: {entity_types}, relation_types: {relation_types}")

#     # Backward-compatible input: entity_types as List[Dict[str, str]] or List[str]
#     if entity_types and isinstance(entity_types[0], dict):
#         entity_types = [e for e in entity_types if str(e.get("type_name", "")).strip()] # return type -> List[Dict[str, str]]

#     # Backward-compatible input: relation_types as list[str]
#     if relation_types and isinstance(relation_types[0], dict):
#         relation_types = [r for r in relation_types if str(r.get("type_name", "")).strip()]

#     # metadata = parsed.get("metadata", {})
#     # if "ontology_id" not in metadata:
#     #     metadata["ontology_id"] = f"onto_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
#     # metadata.setdefault("created_at", datetime.utcnow().isoformat())

#     return {
#         "entity_types": entity_types, # return type -> List[Dict[str, Any]]
#         "relation_types": relation_types, # return type -> List[Dict[str, Any]]
#     }

class OntologyDiscoveryStage:
    """Discovers a local ontology schema from a sample of input documents using LLMs. The discovered ontology defines the entity types, relation types, and their properties that will be used for structured extraction in the next stage. This stage is crucial for enabling domain-agnostic graph construction without requiring manual schema definition upfront."""
    def __init__(self, model: str = "qwen3.5-16k:4b", temperature: float = 0.0):
        self.llm = OpenAILike(
            model=model,
            api_base="http://localhost:11434/v1",
            api_key="ollama",
            is_chat_model=True,
            timeout=300,
            strict=True,
            max_retries=3,
        )

    async def run(
        self,
        documents: List[GraphInputDocument],
        sample_size: int = 4,
    ) -> LocalOntology:
        try:
            sample = documents[: max(1, min(sample_size, len(documents)))]
            sample_payload = [
                {
                    "document_id": d.document_id,
                    "title": d.title,
                    "preview": d.text[:],
                }
                for d in sample
            ]

            prompt = f"""
                You are a domain-agnostic ontology discovery engine.

                Infer a rich local ontology from sample documents.

                Return STRICT JSON with this shape:
                {{
                "entity_types": [
                    {{
                    "type_name": "ENTITY_TYPE",
                    "description": "Short definition",
                    "properties": ["name: brief description"]
                    }}
                ],
                "relation_types": [
                    {{
                    "type_name": "UPPER_SNAKE_CASE",
                    "description": "describes what this relation represents",
                    "source_entity_types": [],
                    "target_entity_types": [],
                    "properties": ["name: brief description"]
                    }}
                ],
                }}

                Rules:
                1. Use UPPER_SNAKE_CASE for names.
                2. Properties MUST be a list of strings formatted as "name: description".
                3. Return Json only

                Sample:
                {json.dumps(sample_payload, ensure_ascii=False)}
                """

            raw = await self.llm.acomplete(prompt) # return type -> str
            text = _strip_json_fences(str(raw)) # return type -> str

            try:
                parsed = json.loads(text) # return type -> Dict[str, Any]
                logger.info(f"Ontology discovery successful. Parsed JSON keys: {parsed}")
            except Exception:
                parsed = {}
                logger.error(f"Failed to parse ontology discovery result: {text}")
                
            structured_json = _structured_properties(parsed) # return type -> Dict[str, Any]
            logger.info(f"Structured properties extracted: {structured_json}")

            # Apply normalization to handle different input shapes and ensure consistent ontology structure for downstream stages. This allows the discovery stage to be more flexible in the output it accepts while still providing a reliable schema for extraction.

            # normalized = _normalize_ontology_shape(parsed) # return type -> Dict[str, Any]
            hydrate_onto = hydrate_ontology(structured_json) # return type -> Dict[str, Any]
            # Returns a REAL Python object, not a dict like access keys by dot notation, type-safe and modify the objects.
            ontology = LocalOntology.model_validate(hydrate_onto) # return type -> LocalOntology
            logging.info(f"Normalized ontology: {ontology}")

            return ontology

        except Exception as e:
            logging.error(f"Error during ontology discovery: {e}")
            return LocalOntology(
                metadata=OntologyMetadata(
                    ontology_id=f"onto_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                    created_at=datetime.utcnow().isoformat(),
                    confidence=0.0,
                    notes=f"discovery_error: {e}",
                ),
                entity_types=[],
                relation_types=[],
            )