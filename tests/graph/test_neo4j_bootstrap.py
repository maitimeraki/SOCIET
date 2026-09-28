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


def test_statement_count_is_ten():
    assert len(_statements()) == 10


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


def test_opinion_lookup_index_present():
    matches = [cypher for cypher, _ in _statements() if "INDEX opinion_round" in cypher]
    assert len(matches) == 1
    assert "(n.dataset_id, n.query_hash, n.round_no)" in matches[0]
