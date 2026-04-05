import json
from datetime import datetime
from typing import List, Dict, Any
from llama_index.llms.openai_like import OpenAILike
from src.graph.models_graph import (
    GraphInputDocument,
    LocalOntology,
    OntologyMetadata,
)


def _strip_json_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.replace("```json", "").replace("```", "").strip()
    return t


def _normalize_ontology_shape(parsed: Dict[str, Any]) -> Dict[str, Any]:
    entity_types = parsed.get("entity_types", [])
    relation_types = parsed.get("relation_types", [])

    # Backward-compatible input: entity_types as list[str]
    if entity_types and isinstance(entity_types[0], str):
        entity_types = [{"type_name": e} for e in entity_types if str(e).strip()]

    # Backward-compatible input: relation_types as list[str]
    if relation_types and isinstance(relation_types[0], str):
        relation_types = [{"type_name": r} for r in relation_types if str(r).strip()]

    metadata = parsed.get("metadata", {})
    if "ontology_id" not in metadata:
        metadata["ontology_id"] = f"onto_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    metadata.setdefault("created_at", datetime.utcnow().isoformat())

    return {
        "metadata": metadata,
        "entity_types": entity_types,
        "relation_types": relation_types,
        "global_constraints": parsed.get("global_constraints", {}),
    }


class OntologyDiscoveryStage:
    """Discovers a local ontology schema from a sample of input documents using LLMs. The discovered ontology defines the entity types, relation types, and their properties that will be used for structured extraction in the next stage. This stage is crucial for enabling domain-agnostic graph construction without requiring manual schema definition upfront."""
    def __init__(self, model: str = "qwen3.5-16k:4b", temperature: float = 0.0):
        self.llm = OpenAILike(
            model=model,
            api_base="http://localhost:11434/v1",
            api_key="ollama",
            is_chat_model=True,
            timeout=300,
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
                    "preview": d.text[:1800],
                }
                for d in sample
            ]

            prompt = f"""
                You are a domain-agnostic ontology discovery engine.

                Infer a rich local ontology from sample documents.

                Return STRICT JSON with this shape:
                {{
                "metadata": {{
                    "ontology_id": "string",
                    "version": "1.0.0",
                    "domain_hint": "string",
                    "confidence": 0.0
                }},
                "entity_types": [
                    {{
                    "type_name": "string",
                    "description": "string",
                    "aliases": [],
                    "properties": [
                        {{
                        "name": "string",
                        "value_type": "string|text|int|float|bool|date|datetime|json|enum|uri|email",
                        "description": "string",
                        "required": false,
                        "multi_valued": false,
                        "is_indexed": false,
                        "is_searchable": true,
                        "unit": null,
                        "default_value": null,
                        "examples": [],
                        "constraints": {{
                            "min_value": null,
                            "max_value": null,
                            "regex": null,
                            "allowed_values": [],
                            "max_length": null
                        }}
                        }}
                    ],
                    "identity": {{
                        "strategy": "hybrid",
                        "key_properties": [],
                        "normalize_name": true,
                        "allow_fuzzy_match": true,
                        "fuzzy_threshold": 0.92
                    }},
                    "merge_policy": {{
                        "conflict_resolution": "highest_confidence",
                        "alias_property": "aliases",
                        "keep_source_provenance": true
                    }},
                    "required_relations": []
                    }}
                ],
                "relation_types": [
                    {{
                    "type_name": "UPPER_SNAKE_CASE",
                    "description": "string",
                    "aliases": [],
                    "source_entity_types": [],
                    "target_entity_types": [],
                    "properties": [],
                    "cardinality": {{"source": "N", "target": "N"}},
                    "inverse_relation": null,
                    "semantics": {{
                        "directed": true,
                        "symmetric": false,
                        "transitive": false,
                        "temporal": false,
                        "confidence_weighted": true
                    }}
                    }}
                ],
                "global_constraints": {{}}
                }}

                Rules:
                - Return JSON only.
                - Keep ontology compact and high-signal.
                - Relation type_name must be UPPER_SNAKE_CASE.

                Sample:
                {json.dumps(sample_payload, ensure_ascii=False)}
                """

            raw = await self.llm.acomplete(prompt)
            text = _strip_json_fences(str(raw))

            try:
                parsed = json.loads(text)
            except Exception:
                parsed = {}
                
            # Apply normalization to handle different input shapes and ensure consistent ontology structure for downstream stages. This allows the discovery stage to be more flexible in the output it accepts while still providing a reliable schema for extraction.

            normalized = _normalize_ontology_shape(parsed)
            ontology = LocalOntology.model_validate(normalized)

            # Minimal fallback if model returns empty
            if not ontology.entity_types:
                ontology.entity_types = [{"type_name": "ENTITY"}]  # pydantic coercion
                ontology = LocalOntology.model_validate(ontology.model_dump())

            if not ontology.relation_types:
                ontology.relation_types = [{"type_name": "RELATED_TO"}]
                ontology = LocalOntology.model_validate(ontology.model_dump())

            return ontology

        except Exception as e:
            print(f"Error during ontology discovery: {e}")
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