"""Invariants for the Neo4j schema bootstrap statements.

The load-bearing assertions are the placeholder/param agreement check and the
literal-indexConfig check. Neo4j rejects parameters inside
``OPTIONS { indexConfig: ... }`` (neo4j/neo4j#12956), and ``ensure_schema``
swallows that rejection into its ``failed`` list — so a parameterized vector
statement silently produces no index. These two assertions are what catch it.
"""
import re

from src.graph.neo4j_bootstrap import _statements

# Capture group only: compare placeholder *names* against params keys, which
# are bare names. Including the `$` would make every legitimately
# parameterized statement compare {'$x'} against {'x'} and fail.
PLACEHOLDER = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")


def _vectors():
    return [(cypher, params) for cypher, params in _statements() if "CREATE VECTOR INDEX" in cypher]


def test_statement_count_is_eleven():
    assert len(_statements()) == 11


def test_every_placeholder_has_a_param_and_every_param_is_used():
    for cypher, params in _statements():
        assert set(PLACEHOLDER.findall(cypher)) == set(params.keys()), cypher


def test_vector_statements_use_literal_index_config():
    vectors = _vectors()
    assert len(vectors) == 2
    for cypher, params in vectors:
        assert "$" not in cypher, cypher
        assert params == {}, cypher
        assert "768" in cypher
        assert "'cosine'" in cypher


def test_document_id_uniqueness_constraint_present():
    matches = [cypher for cypher, _ in _statements() if "CONSTRAINT document_id" in cypher]
    assert len(matches) == 1
    assert "FOR (d:Document) REQUIRE d.document_id IS UNIQUE" in matches[0]
    assert matches[0].startswith("CREATE CONSTRAINT document_id IF NOT EXISTS ")


def test_opinion_lookup_index_present():
    matches = [cypher for cypher, _ in _statements() if "INDEX opinion_round" in cypher]
    assert len(matches) == 1
    assert "(n.dataset_id, n.query_hash, n.round_no)" in matches[0]


def test_entity_vector_index_name_matches_the_llama_index_store():
    """Neo4j allows ONE vector index per label-property pair.

    The llama-index Neo4jPropertyGraphStore owns the vector index on
    `__Entity__.embedding` (its VECTOR_INDEX_NAME constant) and writes the
    embeddings. A bootstrap index with any other name on the same
    label-property pair is rejected as an equivalent schema rule, which
    ``ensure_schema`` swallows — symptom: retrieval dies with
    "There is no such vector schema index". Pin all three consumers to one
    name so an upgrade that renames the store's index fails here, not in
    production.
    """
    from llama_index.graph_stores.neo4j.neo4j_property_graph import VECTOR_INDEX_NAME

    from src.graph.neo4j_bootstrap import ENTITY_EMBEDDINGS_INDEX
    from src.persona import graph_context

    assert ENTITY_EMBEDDINGS_INDEX == VECTOR_INDEX_NAME
    assert graph_context.ENTITY_EMBEDDINGS_INDEX == VECTOR_INDEX_NAME

    entity_stmts = [
        cypher
        for cypher, _ in _statements()
        if "CREATE VECTOR INDEX" in cypher and "__Entity__" in cypher
    ]
    assert len(entity_stmts) == 1
    assert f"CREATE VECTOR INDEX {ENTITY_EMBEDDINGS_INDEX} IF NOT EXISTS" in entity_stmts[0]
