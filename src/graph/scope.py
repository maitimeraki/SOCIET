"""The one Cypher predicate pair that scopes graph reads to a dataset (audit C1).

Entities carry no dataset property: an entity's dataset is the Document it is
DERIVED_FROM (the rule `api/graph_snapshot.py` already uses). Chunks carry
`dataset_id` directly. Every graph read binds `$dataset_id` and uses these.
"""


def entity_in_dataset(var: str = "e") -> str:
    return f"EXISTS {{ ({var})-[:DERIVED_FROM]->(:Document {{dataset_id: $dataset_id}}) }}"


def chunk_in_dataset(var: str = "c") -> str:
    return f"{var}.dataset_id = $dataset_id"


def path_in_dataset(var: str = "p") -> str:
    """Every node on the named path `var` is in the dataset.

    Used on variable-length walks so intermediate hops are scoped too. Nodes
    that own a `dataset_id` (Persona, Opinion, Chunk, Document) pass by that
    property; an entity passes only through its document; anything else fails.
    """
    owned = "x:Persona OR x:Opinion OR x:Chunk OR x:Document"
    return (
        f"ALL(x IN nodes({var}) WHERE "
        f"(({owned}) AND coalesce(x.dataset_id, '') = $dataset_id)"
        f" OR (x:__Entity__ AND {entity_in_dataset('x')}))"
    )
