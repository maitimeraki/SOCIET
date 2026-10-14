"""RQ worker entrypoint: ``python -m src.jobs.worker`` (plan §5).

Containerized in Task 8. RQ workers fork, so this is a Linux/macOS entrypoint —
Windows dev runs the same tasks inline (``QUEUE_MODE=inline``, see
``src/jobs/queue.py``).
"""

import logging

from rq import Worker

from src.jobs import tasks  # noqa: F401 — the module RQ resolves targets from
from src.jobs.queue import QUEUE_NAME, get_queue, get_redis
from src.logging.setup_logging import setup_logging

logger = logging.getLogger(__name__)


def main() -> None:
    setup_logging()
    # The retry policy rides on each enqueued job (`queue._dispatch`); the worker
    # only needs the queue it drains. One job at a time per worker, so the
    # per-user cap and the row lifecycle stay readable in the logs.
    worker = Worker([get_queue()], connection=get_redis())
    logger.info("worker draining queue %r", QUEUE_NAME)
    worker.work()


if __name__ == "__main__":
    main()
