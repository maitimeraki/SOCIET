"""psycopg refuses to run async on Windows' default ProactorEventLoop."""
import asyncio
import sys

import pytest

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(autouse=True)
def clean_queue():
    """No test inherits another's queued jobs from the shared local Redis."""
    from src.jobs import queue as jobs_queue

    queue = jobs_queue.get_queue()
    queue.empty()
    yield
    queue.empty()
