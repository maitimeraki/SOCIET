"""psycopg refuses to run async on Windows' default ProactorEventLoop."""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
