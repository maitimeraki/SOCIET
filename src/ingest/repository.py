"""Uploads row operations (plan §4/§7).

The row is the truth: the ingest route writes it once the bytes are in the
bucket, the extraction worker fills ``extracted_text``, and the documents
endpoint reads it back. Small on purpose — the ingest flow is the only caller.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Upload


def as_uuid(value: object) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def insert_upload(
    session: AsyncSession,
    *,
    upload_id: uuid.UUID,
    user_id: uuid.UUID,
    object_key: str,
    size: int,
    mime: str,
    sha256: str,
    extracted_text: str | None = None,
) -> Upload:
    """Stage one ``uploads`` row on the session (caller commits)."""
    row = Upload(
        id=upload_id,
        user_id=user_id,
        object_key=object_key,
        bytes=size,
        mime=mime,
        sha256=sha256,
        extracted_text=extracted_text,
    )
    session.add(row)
    return row


async def get_upload_row(session: AsyncSession, upload_id: object) -> Upload | None:
    key = as_uuid(upload_id)
    return await session.get(Upload, key) if key is not None else None


async def owned_uploads(
    session: AsyncSession, user_id: uuid.UUID, upload_ids: list[object]
) -> list[Upload]:
    """The caller's rows among ``upload_ids`` (a foreign id is simply absent)."""
    keys = [key for key in (as_uuid(i) for i in upload_ids) if key is not None]
    if not keys:
        return []
    rows = await session.execute(
        select(Upload).where(Upload.user_id == user_id, Upload.id.in_(keys))
    )
    return list(rows.scalars().all())
