from src.graph.models_graph import LocalOntology


def _ontology(type_name: str, props: list[tuple[str, str]]) -> LocalOntology:
    return LocalOntology.model_validate({
        "metadata": {"ontology_id": f"onto-{type_name.lower()}"},
        "entity_types": [{
            "type_name": type_name,
            "description": type_name,
            "properties": [{"name": n, "description": d} for n, d in props],
        }],
        "relation_types": [{
            "type_name": "RELATED_TO",
            "description": "generic",
            "source_entity_types": [type_name],
            "target_entity_types": [type_name],
            "properties": [],
        }],
    })


def test_merge_unions_types_and_dedupes_properties_by_name():
    merged = LocalOntology.merge([
        _ontology("PERSON", [("name", "full name")]),
        _ontology("PERSON", [("name", "dup"), ("age", "years")]),
        _ontology("ORG", [("name", "org name")]),
    ])
    assert merged.entity_labels == ["PERSON", "ORG"]
    assert merged.relation_labels == ["RELATED_TO"]
    assert [p.name for p in merged.entity_types[0].properties] == ["name", "age"]
    assert len(merged.relation_types) == 1


def test_merge_of_empty_list_is_an_empty_ontology():
    merged = LocalOntology.merge([])
    assert merged.entity_labels == []
    assert merged.relation_labels == []
