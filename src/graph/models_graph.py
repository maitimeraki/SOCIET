from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field


class GraphInputDocument(BaseModel):
    document_id: str
    text: str
    title: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# Entity properties are explicit and typed, with constraints and indexing flags.
# Relation properties are first-class, not just edge labels.
# Identity and merge behavior are encoded in ontology, enabling stable normalization.
# Cardinality and source-target compatibility prevent invalid edges.
# Metadata supports versioning, lineage, and confidence over discovered schemas.


# ---------- Property Schema ----------
# Validation rules for property values i.e, Ensures data quality by preventing invalid values before they enter your graph.
class PropertyConstraint(BaseModel):
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    regex: Optional[str] = None
    allowed_values: List[str] = Field(default_factory=list)
    max_length: Optional[int] = None

# Defines a single attribute of an entity or relation
class PropertyDefinition(BaseModel):
    name: str
    value_type: Literal[
        "string",
        "text",
        "int",
        "float",
        "bool",
        "date",
        "datetime",
        "json",
        "enum",
        "uri",
        "email"
    ] = "string"
    description: str = ""
    required: bool = False
    multi_valued: bool = False
    is_indexed: bool = False
    is_searchable: bool = True
    unit: Optional[str] = None
    default_value: Optional[Any] = None
    examples: List[str] = Field(default_factory=list)
    constraints: PropertyConstraint = Field(default_factory=PropertyConstraint)


# ---------- Entity Type Schema ----------
# Determines how to uniquely identify an entity (crucial for avoiding duplicates)
class IdentityRule(BaseModel):
    # Which properties uniquely identify an entity in graph merge/upsert
    strategy: Literal["exact_name", "composite_key", "external_id", "hybrid"] = "hybrid"
    key_properties: List[str] = Field(default_factory=list)   # e.g. ["name", "country"]
    normalize_name: bool = True
    allow_fuzzy_match: bool = True
    fuzzy_threshold: float = 0.92

# Controls how conflicting data is resolved when merging entities
class MergePolicy(BaseModel):
    # How conflicting property values are resolved
    conflict_resolution: Literal["most_recent", "highest_confidence", "majority_vote", "keep_all"] = "highest_confidence"
    alias_property: str = "aliases"
    keep_source_provenance: bool = True

#  Serves as a blueprint for creating and validating entity nodes in your graph.
class EntityTypeDefinition(BaseModel):
    type_name: str
    description: str = ""
    aliases: List[str] = Field(default_factory=list)
    properties: List[PropertyDefinition] = Field(default_factory=list)
    identity: IdentityRule = Field(default_factory=IdentityRule)
    merge_policy: MergePolicy = Field(default_factory=MergePolicy)
    required_relations: List[str] = Field(default_factory=list)   # relation type names expected for this entity


# ---------- Relation Type Schema ----------
# Defines how many entities can be on each side of a relationship
class CardinalityRule(BaseModel):
    source: Literal["1", "N"] = "N"
    target: Literal["1", "N"] = "N"

# Defines logical properties of relationships, which can inform inference and querying (e.g. if A DEPENDS_ON B, then B is a prerequisite for A)
class RelationSemantics(BaseModel):
    directed: bool = True
    symmetric: bool = False
    transitive: bool = False
    temporal: bool = False
    confidence_weighted: bool = True


class RelationTypeDefinition(BaseModel):
    type_name: str
    description: str = ""
    aliases: List[str] = Field(default_factory=list)
    source_entity_types: List[str] = Field(default_factory=list)
    target_entity_types: List[str] = Field(default_factory=list)
    properties: List[PropertyDefinition] = Field(default_factory=list)
    cardinality: CardinalityRule = Field(default_factory=CardinalityRule)
    inverse_relation: Optional[str] = None
    semantics: RelationSemantics = Field(default_factory=RelationSemantics)


# ---------- Ontology Container ----------
#  Allows ontology evolution, A/B testing, and rollback capabilities. Use metadata to track versioning and lineage of discovered schemas.
class OntologyMetadata(BaseModel):
    ontology_id: str
    version: str = "1.0.0"
    domain_hint: Optional[str] = None
    created_at: Optional[str] = None
    source_dataset_id: Optional[str] = None
    confidence: float = 0.7
    notes: str = ""


class PublicOntologyView(BaseModel):
    entity_types: List[str] = Field(default_factory=list)
    relation_types: List[str] = Field(default_factory=list)


class LocalOntology(BaseModel):
    metadata: OntologyMetadata
    entity_types: List[EntityTypeDefinition] = Field(default_factory=list)
    relation_types: List[RelationTypeDefinition] = Field(default_factory=list)
    global_constraints: Dict[str, Any] = Field(default_factory=dict)

    # property decorator -> It allows you to treat a class method like a regular data attribute 
    @property
    def entity_labels(self) -> List[str]:
        return [e.type_name for e in self.entity_types if e.type_name]
    @property
    def relation_labels(self) -> List[str]:
        return [r.type_name for r in self.relation_types if r.type_name]

    def to_public_view(self) -> PublicOntologyView:
        return PublicOntologyView(
            entity_types=[ent.type_name for ent in self.entity_types],
            relation_types=[rel.type_name for rel in self.relation_types]
        )