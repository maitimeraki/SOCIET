"""RQ worker entrypoint: ``python -m src.jobs.worker`` (plan §5).

Containerized in Task 8. RQ workers fork, so this is a Linux/macOS entrypoint —
Windows dev runs the same tasks inline (``QUEUE_MODE=inline``, see
``src/jobs/queue.py``).
"""

import logging
import threading

from rq import Worker

from src.config.settings import get_settings
from src.jobs import tasks  # noqa: F401 — the module RQ resolves targets from
from src.jobs.queue import QUEUE_NAME, get_queue, get_redis
from src.logging.setup_logging import setup_logging
from src.observability import setup_worker_metrics

logger = logging.getLogger(__name__)


def main() -> None:
    setup_logging()
    # Env-gated: serves this process's registry on METRICS_PORT when enabled.
    setup_worker_metrics()
    # The retry policy rides on each enqueued job (`queue._dispatch`); the worker
    # only needs the queue it drains. One job at a time per worker, so the
    # per-user cap and the row lifecycle stay readable in the logs.
    worker = Worker([get_queue()], connection=get_redis())
    if get_settings().queue_mode == "rq":
        try:
            from rq.cron import CronScheduler

            settings = get_settings()
            scheduler = CronScheduler(connection=get_redis())
            # RQ's start() installs SIGINT/SIGTERM handlers, which is
            # main-thread-only; the worker owns those. The daemon thread must
            # not try (it would raise and exit immediately).
            scheduler._install_signal_handlers = lambda: None
            scheduler.register(
                tasks.reconcile_subscriptions,
                queue_name=QUEUE_NAME,
                cron=settings.billing_reconcile_cron,
                name="billing-reconcile",
            )
            scheduler.register(
                tasks.release_expired_reservations,
                queue_name=QUEUE_NAME,
                cron=settings.billing_lease_sweep_cron,
                name="reservation-lease-sweep",
            )
            threading.Thread(target=scheduler.start, daemon=True).start()
        except Exception as exc:
            # A broken scheduler must never take the worker down.
            logger.error("could not start billing crons: %s", exc)
    logger.info("worker draining queue %r", QUEUE_NAME)
    worker.work()


if __name__ == "__main__":
    main()
