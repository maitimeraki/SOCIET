"""A debate job names its corpus by a uuid; a legacy or malformed id fails the job.

Pre-deploy jobs may carry the shared default ``simulation_runtime``. Such a payload
must fail before the reservation is read and before any graph is touched. These
tests stub both seams, so they run without a database.
"""

from unittest.mock import AsyncMock

import pytest

from src.api import debate_api
from src.jobs import tasks


@pytest.fixture
def seams(monkeypatch):
    reservation = AsyncMock()
    runner = AsyncMock()
    monkeypatch.setattr(tasks, "_assert_reservation", reservation)
    monkeypatch.setattr(tasks, "cancel_check", lambda job_id: (lambda: False))
    monkeypatch.setattr(debate_api, "_run_debate_async", runner)
    return reservation, runner


def _payload(graph_id):
    return {"query": "Should we tax carbon?", "config": {}, "graph_id": graph_id}


@pytest.mark.asyncio
@pytest.mark.parametrize("graph_id", ["simulation_runtime", "", None])
async def test_a_malformed_graph_id_fails_the_job(seams, graph_id):
    with pytest.raises((TypeError, ValueError)):
        await tasks._debate_core("job-legacy", _payload(graph_id))


@pytest.mark.asyncio
async def test_a_malformed_graph_id_reads_no_reservation(seams):
    reservation, _ = seams

    with pytest.raises((TypeError, ValueError)):
        await tasks._debate_core("job-legacy", _payload("simulation_runtime"))

    reservation.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_malformed_graph_id_never_reaches_the_runner(seams):
    _, runner = seams

    with pytest.raises((TypeError, ValueError)):
        await tasks._debate_core("job-legacy", _payload("simulation_runtime"))

    runner.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_uuid_graph_id_reaches_the_runner_canonically(seams):
    _, runner = seams
    corpus = "8F5B8C2E-1D2A-4B5C-9D8E-0A1B2C3D4E5F"

    await tasks._debate_core("job-owned", _payload(corpus))

    assert runner.await_args.kwargs["graph_id"] == corpus.lower()
