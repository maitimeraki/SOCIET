"""The boot reaper for stuck verdict retries, at unit level (no database).

The session is a fake that answers each statement as the database would for a single UPDATE ...
RETURNING: it hands back only the rows the statement flipped. The real rows and the real predicate
are the DB-gated tests in test_verdict_retry_db.py.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api import run_doc
from src.billing import units


class _Result:
    def __init__(self, rows=(), rowcount=0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def all(self):
        return list(self._rows)


class _Session:
    """Answers a RETURNING statement with the rows it was given, and any other statement with rowcount 0."""

    def __init__(self, flipped):
        self.flipped = flipped
        self.statements: list[str] = []

    async def execute(self, statement):
        text = str(statement.compile(compile_kwargs={"literal_binds": True}))
        self.statements.append(text)
        if "RETURNING" in text:
            return _Result(rows=self.flipped)
        return _Result(rowcount=0)

    async def commit(self):
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def reaper(monkeypatch):
    """Run the real sweep against the fake session; record each release and audit."""
    flipped_user = uuid.uuid4()
    flipped_id = uuid.uuid4()
    session = _Session(flipped=[SimpleNamespace(id=flipped_id, user_id=flipped_user)])
    released = AsyncMock(return_value=1)
    audit = AsyncMock()
    monkeypatch.setattr(run_doc, "get_session_factory", lambda: (lambda: session))
    monkeypatch.setattr(units, "release_job_reservation", released)
    monkeypatch.setattr("src.audit.record", audit)
    return SimpleNamespace(session=session, released=released, audit=audit,
                           flipped_id=flipped_id, flipped_user=flipped_user)


@pytest.mark.asyncio
async def test_the_reaper_releases_only_the_rows_its_statement_flipped(reaper):
    swept = await run_doc.sweep_interrupted()

    assert [call.args[1] for call in reaper.released.await_args_list] == [reaper.flipped_id]
    assert swept == 1


@pytest.mark.asyncio
async def test_the_reaper_statement_re_checks_the_queued_status_in_the_update(reaper):
    await run_doc.sweep_interrupted()

    stuck = [text for text in reaper.session.statements if "RETURNING" in text]
    assert len(stuck) == 1
    assert "jobs.status = 'queued'" in stuck[0]
    assert "jobs.kind = 'verdict'" in stuck[0]
    assert "jobs.queued_at <" in stuck[0]


@pytest.mark.asyncio
async def test_no_flipped_row_means_no_release_and_no_audit(monkeypatch):
    session = _Session(flipped=[])
    released = AsyncMock(return_value=1)
    audit = AsyncMock()
    monkeypatch.setattr(run_doc, "get_session_factory", lambda: (lambda: session))
    monkeypatch.setattr(units, "release_job_reservation", released)
    monkeypatch.setattr("src.audit.record", audit)

    swept = await run_doc.sweep_interrupted()

    released.assert_not_awaited()
    audit.assert_not_awaited()
    assert swept == 0
