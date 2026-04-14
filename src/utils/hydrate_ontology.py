import uuid
from typing import Dict, Any

def hydrate_ontology(tiny_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transforms minimal LLM output into the complex production schema.
    """
    # Metadata for ontology
    production_ontology = { # return type -> Dict[str, Any]
        "metadata": {
            "ontology_id": str(uuid.uuid4()),
            # "version": "1.0.0",
            # "confidence": 0.95 # Base confidence
        },
        "entity_types": [],
        "relation_types": []
    }

    # Process Entities
    for ent in tiny_json.get("entity_types", []):
        full_entity = {
            "type_name": ent["type_name"],
            "description": ent["description"],
            "properties": [
                {
                    "name": p["name"],
                    "description": p["description"],
                    # "value_type": "string", # Default for 4B models
                    "is_indexed": True,     # System decision
                    "is_searchable": True,
                    # "constraints": {}       # System default
                } for p in ent["properties"]
            ],
            "identity": {
                "strategy": "hybrid",
                "normalize_name": True,
                "allow_fuzzy_match": True
            },
            "merge_policy": { "conflict_resolution": "highest_confidence" }
        }
        production_ontology["entity_types"].append(full_entity) # return type -> List[Dict[str, Any]]

    # Process Relations
    for rel in tiny_json.get("relation_types", []):
        full_rel = { # return type -> Dict[str, Any]
            "type_name": rel["type_name"],
            "source_entity_types": [rel["source_entity_types"][0]] if rel.get("source_entity_types") else [],
            "target_entity_types": [rel["target_entity_types"][0]] if rel.get("target_entity_types") else [],
            "properties":[
               {
                    "name": prop["name"],
                    "description": prop["description"],
                    # "value_type": "string", # Default for 4B models
                    "is_indexed": True,     # System decision
                    "is_searchable": True,
                    # "constraints": {}       # System default
                } for prop in rel["properties"]
            ],
            "semantics": { "directed": True, "confidence_weighted": True }
        }
        production_ontology["relation_types"].append(full_rel)
        
    # production_ontology["global_constraints"] = {
    #     "max_entities": 1000,
    #     "max_relations": 5000,
    #     "enforce_required_relations": True
    # }

    return production_ontology