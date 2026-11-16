"""The job status read is default-deny across modes: only the listed modes serve a result.

No database: run_doc.read_job_doc is faked, and the owner check and projection run for real.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.api import jobs_api
from src.api.jobs_api import served_result

RETRY_LEAK = {"markdown": "# Q", "retry_inputs": {"context": "CTX-SECRET", "turns": []},
              "source_refs": {"1": {"node_id": "N-SECRET"}}, "checks": ["CHECK-SECRET"]}


def test_a_verdict_job_serves_no_result_whatever_it_carries():
    assert served_result("verdict", RETRY_LEAK) is None


@pytest.mark.parametrize("mode", ["mystery", "account_delete", "", None])
def test_an_unlisted_mode_serves_no_result(mode):
    assert served_result(mode, RETRY_LEAK) is None


def test_a_debate_result_goes_through_the_allowlist():
    out = served_result("debate", RETRY_LEAK)

    assert "retry_inputs" not in out and "source_refs" not in out and "checks" not in out


def test_a_listed_graph_mode_passes_its_result_through():
    result = {"dataset_id": "ds-1", "chunks_total": 3}

    assert served_result("ontology", result) == result


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["verdict", "mystery"])
async def test_get_job_serves_no_result_for_an_unlisted_mode(mode):
    user_id = uuid.uuid4()
    doc = {"job_id": str(uuid.uuid4()), "user_id": str(user_id), "mode": mode, "status": "failed",
           "result": RETRY_LEAK, "error": "The report could not be produced."}

    with patch.object(jobs_api.run_doc, "read_job_doc", new=AsyncMock(return_value=doc)):
        served = await jobs_api.get_job(doc["job_id"], user=SimpleNamespace(id=user_id))

    assert served["result"] is None
    assert "CTX-SECRET" not in repr(served) and "N-SECRET" not in repr(served)


@pytest.mark.asyncio
async def test_get_job_serves_a_debate_result_only_through_the_allowlist():
    user_id = uuid.uuid4()
    doc = {"job_id": str(uuid.uuid4()), "user_id": str(user_id), "mode": "debate", "status": "complete",
           "result": {**RETRY_LEAK, "converged": True}, "error": None}

    with patch.object(jobs_api.run_doc, "read_job_doc", new=AsyncMock(return_value=doc)):
        served = await jobs_api.get_job(doc["job_id"], user=SimpleNamespace(id=user_id))

    assert served["result"] == {"markdown": "# Q", "converged": True}
