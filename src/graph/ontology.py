import sys
import os
import uuid
import json
import logging
from typing import List, Dict, Any, get_args
from llama_index.llms.openai_like import OpenAILike
from src.logging.setup_logging import setup_logging
from src.utils.hydrate_ontology import hydrate_ontology
from src.llm.config_llm import LLMConfig
from src.graph.models_graph import (
    ProcessedChunk,
    LocalOntology,
    PropertyDefinition,
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

# The accepted value kinds come from the one vocabulary (PropertyDefinition) — never re-list them.
_VALID_KINDS = set(get_args(PropertyDefinition.model_fields["value_type"].annotation))


def _parse_prop(raw: str) -> dict:
    # "name: value_type: description" | "name: description" | "name"
    parts = [p.strip() for p in raw.split(":", 2)]
    if len(parts) == 3 and parts[1].lower() in _VALID_KINDS:
        return {"name": parts[0], "value_type": parts[1].lower(), "description": parts[2]}
    if len(parts) >= 2:
        return {"name": parts[0], "value_type": "string", "description": parts[1]}
    return {"name": raw.strip(), "value_type": "string", "description": ""}


def _structured_properties(llm_data: Dict[str, Any]) -> Dict[str, Any]:
    # Transform the flat property strings into the strict Pydantic shapes.
    for key in ("entity_types", "relation_types"):
        for block in llm_data.get(key, []):
            block["properties"] = [_parse_prop(p) for p in block.get("properties", [])]
    return llm_data

async def discover_ontology(
    chunks: List[ProcessedChunk],
    model: str = LLMConfig.analysis_model,
    sample_size: int = 10,
) -> LocalOntology:
    """
    Discover a local ontology schema from input chunks using LLM.

    Args:
        chunks: List of processed document chunks to analyze
        model: LLM model to use for discovery (default: LLMConfig.analysis_model)
        sample_size: Number of chunks to sample for discovery (default: 10)

    Returns:
        LocalOntology with discovered entity_types, relation_types, and property_definitions
    """
    stage = OntologyDiscoveryStage(model=model)
    return await stage.run(documents=chunks, sample_size=sample_size)


def discover_ontology_sync(
    chunks: List[ProcessedChunk],
    model: str = LLMConfig.analysis_model,
    sample_size: int = 10,
) -> LocalOntology:
    """
    Synchronous wrapper for discover_ontology using asyncio.
    """
    import asyncio
    return asyncio.run(discover_ontology(chunks, model, sample_size))


class OntologyDiscoveryStage:
    """Discovers a local ontology schema from a sample of input documents using LLMs. The discovered ontology defines the entity types, relation types, and their properties that will be used for structured extraction in the next stage. This stage is crucial for enabling domain-agnostic graph construction without requiring manual schema definition upfront."""
    def __init__(self, model: str = LLMConfig.analysis_model, temperature: float = 0.7, timeout: float = 60.0):
        conversation_session_id = str(uuid.uuid4())
        self.llm = OpenAILike(
            model=model,
            api_base=LLMConfig.nvidia_nim_base_url or "https://integrate.api.nvidia.com/v1",
            api_key=LLMConfig.nvidia_nim_api_key,
            is_chat_model=True,
            timeout=timeout, # was 480 — must fit inside the caller's wait_for window
            max_retries=1, # was llama-index default 3 × SDK default 3 (stacked)
            strict=True, # Reliable Structured Output
            temperature=temperature, # Deterministic output for ontology discovery
            additional_kwargs={
                "seed": 42, # Fixed seed for reproducibility
                "extra_headers":{
               "x-opencode-session": conversation_session_id
                }
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
                    "properties": ["name: value_type: brief description"]
                    }}
                ],
                "relation_types": [
                    {{
                    "type_name": "UPPER_SNAKE_CASE",
                    "description": "describes what this relation represents",
                    "source_entity_types": [],
                    "target_entity_types": [],
                    "properties": ["name: value_type: brief description"]
                    }}
                ],
                }}

                Rules:
                1. Use UPPER_SNAKE_CASE for names of properties of relations.
                2. Every property MUST be "name: value_type: description" where value_type is one of:
                   string, int, float, bool, date, datetime, money, quantity, percentage, enum.
                   Attribute values (prices, dates, revenues, counts, percentages) are PROPERTIES, never entity types.
                3. Return Json only

                Sample:
                {json.dumps(sample_payload, ensure_ascii=False)}
                """

            raw = await self.llm.acomplete(prompt) # return type -> str
            text = _strip_json_fences(str(raw)) # return type -> str

            try:
                parsed = json.loads(text) # return type -> Dict[str, Any]
                logger.info(f"Ontology discovery successful. Parsed JSON keys: {parsed}")
            except Exception as exc:
                logger.error("Unparseable ontology discovery reply: %s", text[:500])
                raise RuntimeError(f"unparseable ontology discovery reply: {exc}") from exc
                
            structured_json = _structured_properties(parsed) # return type -> Dict[str, Any]
            logger.info(f"Structured properties extracted: {structured_json}")

            # Apply normalization to handle different input shapes and ensure consistent ontology structure for downstream stages. This allows the discovery stage to be more flexible in the output it accepts while still providing a reliable schema for extraction.

            # normalized = _normalize_ontology_shape(parsed) # return type -> Dict[str, Any]
            hydrate_onto = hydrate_ontology(structured_json) # return type -> Dict[str, Any]
            # Returns a REAL Python object, not a dict like access keys by dot notation, type-safe and modify the objects.
            ontology = LocalOntology.model_validate(hydrate_onto) # return type -> LocalOntology
            logging.info(f"Normalized ontology: {ontology}")

            return ontology

        except Exception as exc:
            logger.error(f"Error during ontology discovery: {exc}")
            raise RuntimeError(str(exc)) from exc