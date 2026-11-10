"""Age-based retention purge (plan §12) — the CLI twin of the RQ task.

Deletes raw upload objects older than ``RETENTION_RAW_UPLOADS_DAYS`` (the rows
keep their metadata and extracted text), fully deletes runs older than
``RETENTION_RUNS_DAYS``, and trims ``audit_log`` older than
``RETENTION_AUDIT_DAYS``. The logic is shared with
``src.jobs.tasks.purge_retention`` — this script is only the argv wrapper.

    python scripts/purge_retention.py --dry-run   # print counts, write nothing
    python scripts/purge_retention.py             # apply

NO cron is set up here: scheduling is deployment's job. Either run this script
on a timer (systemd timer / cron / k8s CronJob) or push the RQ task onto the
worker's queue from a scheduler
(``get_queue().enqueue(src.jobs.tasks.purge_retention)``). The dry run is the
recommended pre-flight before wiring the timer.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# psycopg refuses to run async on Windows' default ProactorEventLoop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the counts that WOULD be purged and write nothing",
    )
    args = parser.parse_args()

    from src.jobs.tasks import purge_retention

    counts = purge_retention(dry_run=args.dry_run)
    print(json.dumps({"dry_run": args.dry_run, **counts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
