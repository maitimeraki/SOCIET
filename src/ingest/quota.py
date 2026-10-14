"""Per-user upload quota (plan §7, deliverable 2).

Usage is computed in SQL — ``SUM(bytes)`` / ``COUNT(*)`` over the user's
``uploads`` rows for the current calendar month — never by counting in memory.
The caller enforces the quota at upload time, before extraction, and maps a
`QuotaExceeded` onto the uniform 429 contract with a `Retry-After` header.
"""

import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import get_settings
from src.db.models import Upload

_RETRY_AFTER_CAP_SECONDS = 86_400  # 24 h


class QuotaExceeded(Exception):
    """The incoming upload would exceed the user's calendar-month quota."""

    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Upload quota exceeded; retry after {retry_after}s")


def _month_start(now: datetime.datetime) -> datetime.datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def retry_after_seconds(now: datetime.datetime | None = None) -> int:
    """Seconds until the month resets, capped at 24 h (and floored at 1)."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    next_month = _month_start(_month_start(now) + datetime.timedelta(days=32))
    seconds = int((next_month - now).total_seconds())
    return max(1, min(seconds, _RETRY_AFTER_CAP_SECONDS))


async def usage_this_month(session: AsyncSession, user_id: object) -> tuple[int, int]:
    """``(bytes_used, files_used)`` for the current calendar month, from SQL."""
    start = _month_start(datetime.datetime.now(datetime.timezone.utc))
    result = await session.execute(
        select(
            func.coalesce(func.sum(Upload.bytes), 0),
            func.count(),
        ).where(Upload.user_id == user_id, Upload.created_at >= start)
    )
    total_bytes, total_files = result.one()
    return int(total_bytes), int(total_files)


async def enforce_upload_quota(
    session: AsyncSession,
    user_id: object,
    incoming_bytes: int = 0,
    incoming_files: int = 0,
) -> None:
    """Raise `QuotaExceeded` if adding the incoming upload would break the quota.

    Called at upload time, before any storage or extraction happens.
    """
    settings = get_settings()
    used_bytes, used_files = await usage_this_month(session, user_id)
    if (
        used_bytes + incoming_bytes > settings.upload_quota_bytes_month
        or used_files + incoming_files > settings.upload_quota_files_month
    ):
        raise QuotaExceeded(retry_after_seconds())
