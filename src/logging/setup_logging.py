# src/utils/logger.py
import contextvars
import logging
import sys

#: The correlation id of whatever is executing — the request's, stamped by the
#: API middleware, or the enqueuing request's, restored by a queue worker (plan
#: §10: worker logs join the trace of the request that queued the job).
CORRELATION_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)


def set_correlation_id(value: str | None):
    """Bind the id for this execution; returns the token to ``reset`` it."""
    return CORRELATION_ID.set(value)


def reset_correlation_id(token) -> None:
    CORRELATION_ID.reset(token)


class CorrelationIdFilter(logging.Filter):
    """Stamps the current correlation id on every record that lacks one."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "correlation_id", None):
            record.correlation_id = CORRELATION_ID.get() or "-"
        return True


def setup_logging():
    """Setup logging with handler clearing to prevent duplication"""

    # Get or create root logger
    logger = logging.getLogger("fastapi_app")

    # ✅ CRITICAL: Clear existing handlers
    if logger.hasHandlers():
        logger.handlers.clear()

    logger.setLevel(logging.INFO)

    # Remove all handlers from root logger too
    root_logger = logging.getLogger()
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Create fresh handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(levelname)s - [%(correlation_id)s] %(message)s')
    )
    console_handler.addFilter(CorrelationIdFilter())

    logger.addHandler(console_handler)
    root_logger.addHandler(console_handler)

    return logger
