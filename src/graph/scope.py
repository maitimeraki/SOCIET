"""The one Cypher predicate pair that scopes graph reads to a dataset (audit C1).

Entities carry no dataset property: an entity's dataset is the Document it is
DERIVED_FROM (the rule `api/graph_snapshot.py` already uses). Chunks carry
`dataset_id` directly. Every graph read binds `$dataset_id` and uses these.
"""


def entity_in_dataset(var: str = "e") -> str:
    return f"EXISTS {{ ({var})-[:DERIVED_FROM]->(:Document {{dataset_id: $dataset_id}}) }}"


def chunk_in_dataset(var: str = "c") -> str:
    return f"{var}.dataset_id = $dataset_id"
