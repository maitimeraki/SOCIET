"""Task 5: backfill of the legacy runtime JSON into rows (plan §13).

The legacy files are read-only history; the script writes through the same
store the API uses and is re-run safe.
"""
import asyncio
import json
import os
import sys
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select

from scripts import migrate_runtime_json as migrate
from src.api import run_doc
from src.db.engine import get_session_factory
from src.db.models import RunEvent, User

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

requires_db = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set")

pytestmark = [requires_db, pytest.mark.asyncio]

JOB_ID = str(uuid.uuid4())
RUN_ID = str(uuid.uuid4())
FAILED_RUN_ID = str(uuid.uuid4())

JOB_DOC = {
    "job_id": JOB_ID,
    "mode": "build_graph",
    "status": "completed",
    "progress": 1.0,
    "stage": "completed",
    "error": None,
    "result": {"dataset_id": "ds-1", "chunks_total": 3, "docs_built": 3},
}

DEBATE_DOC = {
    "run_id": RUN_ID,
    "created_at": "2026-10-01T10:00:00+00:00",
    "query": "Should we expand into Europe?",
    "dataset_id": "ds-1",
    "config": {"max_rounds": 2},
    "status": "complete",
    "events": [
        {"type": "stage", "stage": "round", "index": 0},
        {"type": "stage", "stage": "round", "index": 1},
        {"type": "complete", "verdict": "Expand."},
    ],
    "result": {"rounds_executed": 2, "converged": True, "confidence_score": 0.81},
}

FAILED_DEBATE_DOC = {
    "run_id": FAILED_RUN_ID,
    "created_at": "2026-10-02T10:00:00+00:00",
    "query": "Should we cut the budget?",
    "dataset_id": "ds-2",
    "config": {},
    "status": "failed",
    "events": [{"type": "error", "error": "orchestrator exploded"}],
    "result": None,
}


@pytest_asyncio.fixture
async def owner(db):
    factory = get_session_factory()
    async with factory() as session:
        user = User(
            email=f"run-truth-{uuid.uuid4().hex[:10]}@example.com",
            password_hash="not-a-real-hash",
        )
        session.add(user)
        await session.commit()
        account = SimpleNamespace(id=user.id)
    yield account
    async with factory() as session:
        await session.execute(delete(User).where(User.id == account.id))
        await session.commit()


@pytest.fixture
def legacy_tree(tmp_path, monkeypatch):
    """A miniature legacy store: two debate docs, one job doc."""
    jobs = tmp_path / "jobs"
    debates = tmp_path / "debates"
    jobs.mkdir()
    debates.mkdir()
    (jobs / f"{JOB_ID}.json").write_text(json.dumps(JOB_DOC), encoding="utf-8")
    (debates / f"{RUN_ID}.json").write_text(json.dumps(DEBATE_DOC), encoding="utf-8")
    (debates / f"{FAILED_RUN_ID}.json").write_text(json.dumps(FAILED_DEBATE_DOC), encoding="utf-8")
    monkeypatch.setattr(migrate, "JOBS_DIR", jobs)
    monkeypatch.setattr(migrate, "DEBATES_DIR", debates)
    return tmp_path


async def _event_rows(run_id: str) -> list[RunEvent]:
    async with get_session_factory()() as session:
        return (
            await session.execute(
                select(RunEvent).where(RunEvent.run_id == uuid.UUID(run_id)).order_by(RunEvent.seq)
            )
        ).scalars().all()


async def test_migrate_writes_rows_matching_the_files(legacy_tree, owner):
    assert await migrate._migrate(owner.id, dry_run=False) == 0

    job = await run_doc.read_job_doc(JOB_ID)
    assert job["user_id"] == str(owner.id)
    assert (job["mode"], job["status"], job["result"]) == ("build_graph", "completed", JOB_DOC["result"])

    run = await run_doc.read_run_doc(RUN_ID)
    assert (run["query"], run["dataset_id"], run["config"]) == (
        DEBATE_DOC["query"], "ds-1", {"max_rounds": 2},
    )
    assert run["result"] == DEBATE_DOC["result"]
    assert [event["type"] for event in run["events"]] == ["stage", "stage", "complete"]
    rows = await _event_rows(RUN_ID)
    assert [row.seq for row in rows] == [0, 1, 2, 3]  # 0 is the run_meta row
    assert rows[0].type == "run_meta"

    failed = await run_doc.read_run_doc(FAILED_RUN_ID)
    assert failed["status"] == "failed"
    # The stream's error event is lifted onto the jobs row (runs have no error).
    async with get_session_factory()() as session:
        head = await run_doc.read_run_head(FAILED_RUN_ID)
    assert head["error"] == "orchestrator exploded"


async def test_rerun_is_safe_and_never_clobbers(legacy_tree, owner):
    await migrate._migrate(owner.id, dry_run=False)

    # A live run moves on after the first migration; the stale file must not win.
    await run_doc.write_run_doc({**DEBATE_DOC, "user_id": str(owner.id), "status": "failed"})

    assert await migrate._migrate(owner.id, dry_run=False) == 0

    run = await run_doc.read_run_doc(RUN_ID)
    assert run["status"] == "failed"
    async with get_session_factory()() as session:
        meta_rows = (
            await session.execute(
                select(func.count()).select_from(RunEvent).where(
                    RunEvent.run_id == uuid.UUID(RUN_ID), RunEvent.type == "run_meta"
                )
            )
        ).scalar_one()
    assert meta_rows == 1


async def test_dry_run_writes_nothing(legacy_tree, owner, capsys):
    assert await migrate._migrate(owner.id, dry_run=True) == 0

    printed = capsys.readouterr().out
    assert "[dry-run]" in printed
    assert "would write: 3" in printed
    assert await run_doc.read_job_doc(JOB_ID) is None
    assert await run_doc.read_run_doc(RUN_ID) is None


async def test_verify_passes_and_checks_verdicts(legacy_tree, owner, capsys):
    await migrate._migrate(owner.id, dry_run=False)
    capsys.readouterr()

    assert await migrate._verify(owner.id, spot_checks=5) == 0

    printed = capsys.readouterr().out
    assert "jobs rows 1/1" in printed
    assert "runs rows 2/2" in printed
    assert "run_events rows 6 present, 6 expected" in printed
    assert "verdict spot-checks 1/1 byte-for-byte" in printed
    assert "verify: OK" in printed


async def test_verify_flags_a_missing_row(legacy_tree, owner, capsys):
    await migrate._migrate(owner.id, dry_run=False)
    async with get_session_factory()() as session:
        await session.execute(delete(RunEvent).where(RunEvent.run_id == uuid.UUID(RUN_ID)))
        await session.commit()
    capsys.readouterr()

    assert await migrate._verify(owner.id, spot_checks=5) == 1

    printed = capsys.readouterr().out
    assert "PROBLEM" in printed
    assert "verify: FAILED" in printed


async def test_unknown_owner_is_an_error(legacy_tree):
    with pytest.raises(SystemExit) as exc:
        await migrate._owner_id("nobody@example.com")
    assert "no account with email" in str(exc.value)


async def test_a_corrupt_legacy_file_is_refused(legacy_tree, owner, monkeypatch):
    (migrate.DEBATES_DIR / "broken.json").write_text("{ not json", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        await migrate._migrate(owner.id, dry_run=False)
    assert "unreadable legacy file" in str(exc.value)
