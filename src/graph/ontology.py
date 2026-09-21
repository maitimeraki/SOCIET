import sys
import json
import logging
from datetime import datetime
from typing import List, Dict, Any
from llama_index.llms.openai_like import OpenAILike
from src.logging.setup_logging import setup_logging
from src.utils.hydrate_ontology import hydrate_ontology
from src.graph.models_graph import (
    ProcessedChunk,
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
# logger = logging.getLogger(__name__)
logger = setup_logging()  # Ensure logging is configured with handler clearing to prevent duplication

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

async def discover_ontology(
    chunks: List[ProcessedChunk],
    model: str = "gemma4-e4b-64k:latest",
    sample_size: int = 10,
) -> LocalOntology:
    """
    Discover a local ontology schema from input chunks using LLM.

    Args:
        chunks: List of processed document chunks to analyze
        model: LLM model to use for discovery (default: gemma4-e4b-64k:latest)
        sample_size: Number of chunks to sample for discovery (default: 10)

    Returns:
        LocalOntology with discovered entity_types, relation_types, and property_definitions
    """
    stage = OntologyDiscoveryStage(model=model)
    return await stage.run(documents=chunks, sample_size=sample_size)


def discover_ontology_sync(
    chunks: List[ProcessedChunk],
    model: str = "gemma4-e4b-64k:latest",
    sample_size: int = 10,
) -> LocalOntology:
    """
    Synchronous wrapper for discover_ontology using asyncio.
    """
    import asyncio
    return asyncio.run(discover_ontology(chunks, model, sample_size))


class OntologyDiscoveryStage:
    """Discovers a local ontology schema from a sample of input documents using LLMs. The discovered ontology defines the entity types, relation types, and their properties that will be used for structured extraction in the next stage. This stage is crucial for enabling domain-agnostic graph construction without requiring manual schema definition upfront."""
    def __init__(self, model: str = "gemma4-e4b-64k:latest", temperature: float = 0.7):
        self.llm = OpenAILike(
            model=model,
            api_base="http://localhost:11434/v1",
            api_key="ollama",
            is_chat_model=True,
            timeout=480,
            strict=True, # Reliable Structured Output
            temperature=temperature, # Deterministic output for ontology discovery
            additional_kwargs={
                "seed": 42, # Fixed seed for reproducibility
            }
        )

    async def run(
        self,
        documents: List[ProcessedChunk],
        sample_size: int = 4,
    ) -> LocalOntology:
        try:
            sample = documents[: max(1, min(sample_size, len(documents)))]
            sample_payload = [
                {
                    "document_id": d.parent_doc_id,
                    "title": d.metadata.get("title", "Untitled Document"),
                    "preview": d.content[:],
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
                    "type_name": "EntityTypeName",
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
                1. Use UPPER_SNAKE_CASE for names of properties of relations.
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
                    created_at=datetime.utcnow().isoformat()
                ),
                entity_types=[],
                relation_types=[],
            )