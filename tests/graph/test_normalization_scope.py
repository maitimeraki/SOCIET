"""The normalize writes that can touch another tenant's nodes, checked with a fake session (no Neo4j).

The live behaviour of APOC mergeNodes is not exercised here; these tests pin what the Python
side sends and when it refuses.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.graph.normalization import GraphNormalizationStage, MergeCandidate


class _Result:
    async def data(self):
        return []


class _Tx:
    def __init__(self, log):
        self.log = log
        self.committed = False

    async def run(self, query, params=None):
        self.log.append((str(query), dict(params or {})))
        return _Result()

    async def commit(self):
        self.committed = True


class _TxContext:
    def __init__(self, log):
        self.tx = _Tx(log)

    async def __aenter__(self):
        return self.tx

    async def __aexit__(self, *exc):
        return False


class _Session:
    def __init__(self, log):
        self.log = log

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def begin_transaction(self):
        return _TxContext(self.log)

    async def run(self, query, params=None):
        self.log.append((str(query), dict(params or {})))
        return _Result()


class _Driver:
    def __init__(self, log):
        self.log = log

    def session(self, database=None):
        return _Session(self.log)


def _stage(log) -> GraphNormalizationStage:
    stage = GraphNormalizationStage.__new__(GraphNormalizationStage)
    stage.driver = _Driver(log)
    stage.config = SimpleNamespace(neo4j_database="neo4j")
    stage.batch_size = 10
    stage.compute_signals = AsyncMock(return_value={"aggregate_confidence": 0.99})
    return stage


def _node(node_id: str, dataset_id, name: str = "acme") -> MergeCandidate:
    props = {"name": name} if dataset_id is None else {"name": name, "dataset_id": dataset_id}
    return MergeCandidate(node_id=node_id, labels=["Organization"], properties=props)


def _merge_queries(log):
    return [(query, params) for query, params in log if "mergeNodes" in query]


@pytest.mark.asyncio
async def test_the_merge_matches_only_nodes_of_the_survivors_dataset():
    log = []
    survivor, other = _node("4:a:1", "ds-A"), _node("4:a:2", "ds-A")

    result = await _stage(log).destructive_merge(survivor, [other])

    assert result["status"] == "merged"
    ((query, params),) = _merge_queries(log)
    assert "AND n.dataset_id = $dataset_id" in query
    assert params["dataset_id"] == "ds-A"


@pytest.mark.asyncio
async def test_a_group_that_mixes_datasets_is_refused_before_any_write():
    log = []
    survivor, other = _node("4:a:1", "ds-A"), _node("4:a:2", "ds-B")

    result = await _stage(log).destructive_merge(survivor, [other])

    assert result["status"] == "refused"
    assert result["audit_id"] is None
    assert log == []


@pytest.mark.asyncio
async def test_a_survivor_without_a_dataset_is_refused_before_any_write():
    log = []
    survivor, other = _node("4:a:1", None), _node("4:a:2", None)

    result = await _stage(log).destructive_merge(survivor, [other])

    assert result["status"] == "refused"
    assert log == []


@pytest.mark.asyncio
async def test_a_review_row_carries_the_groups_dataset_id():
    log = []
    group = [_node("4:a:1", "ds-A"), _node("4:a:2", "ds-A")]

    review_id = await _stage(log).enqueue_for_review(group, {"aggregate_confidence": 0.1}, reason="low")

    assert review_id
    ((query, params),) = [(q, p) for q, p in log if "MergeReview" in q]
    assert "dataset_id: $dataset_id" in query
    assert params["dataset_id"] == "ds-A"
