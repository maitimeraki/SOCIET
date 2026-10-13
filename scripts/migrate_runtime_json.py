"""Backfill the legacy runtime JSON mirrors into Postgres (plan §13).

Reads ``src/api/runtime/jobs/*.json`` + ``src/api/runtime/debates/*.json`` —
the retired JSON store, now read-only history — and writes rows through the
same store the API uses (``src/api/run_doc.py``):

    job doc     -> jobs row + runs row (state in the jsonb; no columns exist)
    debate doc  -> jobs + runs row, plus one run_events row per ``events[]``
                   element (seq = index + 1; seq 0 is the run_meta row)

Owner assignment: ``--owner-email`` names an EXISTING account (single-tenant
migration) — every migrated row belongs to it. Re-run safe: a file whose id
already has a row is skipped, never overwritten (a live run must not be
clobbered by its stale legacy file).

    python scripts/migrate_runtime_json.py --owner-email you@example.com
    python scripts/migrate_runtime_json.py --owner-email you@example.com --dry-run
    python scripts/migrate_runtime_json.py --owner-email you@example.com --verify
"""
import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    # psycopg refuses to run async on Windows' default ProactorEventLoop.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import func, select  # noqa: E402

from src.api import run_doc  # noqa: E402
from src.db.engine import get_session_factory  # noqa: E402
from src.db.models import RunEvent, User  # noqa: E402

JOBS_DIR = ROOT / "src/api/runtime/jobs"
DEBATES_DIR = ROOT / "src/api/runtime/debates"
DEFAULT_SPOT_CHECKS = 5


def _files(directory: Path) -> list[Path]:
    return sorted(directory.glob("*.json")) if directory.exists() else []


def _load(path: Path) -> dict:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"unreadable legacy file {path}: {exc}")
    if not isinstance(doc, dict):
        raise SystemExit(f"legacy file {path} is not a JSON object")
    return doc


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _mtime_iso(path: Path) -> str:
    import datetime

    return datetime.datetime.fromtimestamp(
        path.stat().st_mtime, tz=datetime.timezone.utc
    ).isoformat()


async def _owner_id(email: str) -> uuid.UUID:
    async with get_session_factory()() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
    if user is None:
        raise SystemExit(
            f"no account with email {email!r} — create it first (POST /api/v1/auth/signup), then re-run"
        )
    return user.id


def _debate_doc(path: Path, doc: dict, owner: uuid.UUID) -> tuple[dict, list[dict]]:
    """The run doc + its events, with the owner assigned and the error lifted
    out of the stream (runs have no error column — the jobs row carries it)."""
    events = [event for event in (doc.get("events") or []) if isinstance(event, dict)]
    doc = dict(doc)
    doc["run_id"] = str(doc.get("run_id") or path.stem)
    doc["user_id"] = str(owner)
    doc["events"] = []
    error_event = next((e for e in reversed(events) if e.get("type") == "error"), None)
    if error_event and not doc.get("error"):
        doc["error"] = error_event.get("error")
    return doc, events


async def _migrate(owner: uuid.UUID, dry_run: bool) -> int:
    written = skipped = 0

    for path in _files(JOBS_DIR):
        doc = _load(path)
        doc["job_id"] = str(doc.get("job_id") or path.stem)
        if await run_doc.read_job_doc(doc["job_id"]) is not None:
            skipped += 1
            continue
        doc["user_id"] = str(owner)
        # Job docs predate any timestamp field; the file's mtime is the only
        # honest queued_at (the brief's `queued_at <- created_at`).
        doc.setdefault("created_at", _mtime_iso(path))
        if dry_run:
            print(
                f"[dry-run] jobs/{path.name} -> jobs+runs rows "
                f"(kind={doc.get('mode')}, status={doc.get('status')})"
            )
        else:
            await run_doc.write_job_doc(doc)
        written += 1

    for path in _files(DEBATES_DIR):
        doc, events = _debate_doc(path, _load(path), owner)
        if await run_doc.read_run_head(doc["run_id"]) is not None:
            skipped += 1
            continue
        if dry_run:
            print(
                f"[dry-run] debates/{path.name} -> jobs+runs rows + {len(events)} run_events rows "
                f"(status={doc.get('status')})"
            )
        else:
            await run_doc.write_run_doc(doc)
            for index, event in enumerate(events):
                await run_doc.append_run_event(doc["run_id"], index + 1, event)
        written += 1

    verb = "would write" if dry_run else "wrote"
    print(f"{verb}: {written} - skipped (already present): {skipped}")
    return 0


async def _verify(owner: uuid.UUID | None, spot_checks: int) -> int:
    problems: list[str] = []
    owned_mismatch = 0

    job_files = _files(JOBS_DIR)
    jobs_found = 0
    for path in job_files:
        doc = _load(path)
        job_id = str(doc.get("job_id") or path.stem)
        row = await run_doc.read_job_doc(job_id)
        if row is None:
            problems.append(f"jobs/{path.name}: no jobs row for {job_id}")
            continue
        jobs_found += 1
        if owner is not None and row["user_id"] != str(owner):
            owned_mismatch += 1

    debate_files = _files(DEBATES_DIR)
    runs_found = 0
    expected_events = 0
    run_ids: list[uuid.UUID] = []
    checked_verdicts = 0
    verdict_matches = 0
    for path in debate_files:
        doc = _load(path)
        run_id = str(doc.get("run_id") or path.stem)
        row = await run_doc.read_run_doc(run_id)
        if row is None:
            problems.append(f"debates/{path.name}: no runs row for {run_id}")
            continue
        runs_found += 1
        run_ids.append(uuid.UUID(row["run_id"]))
        if owner is not None and row["user_id"] != str(owner):
            owned_mismatch += 1
        source_events = [e for e in (doc.get("events") or []) if isinstance(e, dict)]
        expected_events += len(source_events) + 1  # + the run_meta row
        if _canonical(row["events"]) != _canonical(source_events):
            problems.append(f"debates/{path.name}: events differ from the source JSON")
        if checked_verdicts < spot_checks and doc.get("result") is not None:
            checked_verdicts += 1
            if _canonical(row["result"]) == _canonical(doc["result"]):
                verdict_matches += 1
            else:
                problems.append(f"debates/{path.name}: verdict differs from the source JSON")

    present_events = 0
    if run_ids:
        async with get_session_factory()() as session:
            present_events = (
                await session.execute(
                    select(func.count())
                    .select_from(RunEvent)
                    .where(RunEvent.run_id.in_(run_ids))
                )
            ).scalar_one()

    print(f"verify: jobs rows {jobs_found}/{len(job_files)} legacy job files")
    print(f"verify: runs rows {runs_found}/{len(debate_files)} legacy debate files")
    print(
        f"verify: run_events rows {present_events} present, {expected_events} expected "
        f"(streamed + one run_meta per run)"
    )
    print(f"verify: verdict spot-checks {verdict_matches}/{checked_verdicts} byte-for-byte")
    if owner is not None:
        print(f"verify: ownership mismatches: {owned_mismatch}")
    if present_events != expected_events:
        problems.append(f"run_events count {present_events} != expected {expected_events}")
    if jobs_found != len(job_files):
        problems.append(f"jobs rows {jobs_found} != files {len(job_files)}")
    if runs_found != len(debate_files):
        problems.append(f"runs rows {runs_found} != files {len(debate_files)}")

    for problem in problems:
        print(f"verify: PROBLEM: {problem}")
    print("verify: OK" if not problems else f"verify: FAILED ({len(problems)} problem(s))")
    return 0 if not problems else 1


async def _main(args: argparse.Namespace) -> int:
    owner = await _owner_id(args.owner_email)
    if args.verify:
        return await _verify(owner, args.spot_checks)
    return await _migrate(owner, args.dry_run)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--owner-email", required=True, help="an EXISTING account that owns the migrated rows")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print what would be written; write nothing")
    mode.add_argument("--verify", action="store_true", help="check rows against the legacy files; write nothing")
    parser.add_argument("--spot-checks", type=int, default=DEFAULT_SPOT_CHECKS, help="verdict spot-checks in --verify")
    return asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
