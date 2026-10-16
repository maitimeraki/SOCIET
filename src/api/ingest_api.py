"""Ingest API: accept uploads and hand extraction to the worker (R17).

Both routes validate at the trust boundary and *enqueue* — they never extract:
``POST /files`` magic-byte-checks each upload, enforces the per-user quota, puts
the bytes in the object bucket, writes the ``uploads`` rows, and queues one
``extract_upload`` job; ``POST /url`` runs the SSRF guard and queues the fetch.
Both answer ``202 {job_id, status: "queued"}`` (uniform with the debate
enqueue). The extracted payloads are read back through ``GET /documents``.
"""

import asyncio
import hashlib
import json
import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.jobs_api import enqueue_or_http
from src.audit import client_ip
from src.audit import record as audit_record
from src.auth.cookies import verify_csrf
from src.auth.deps import current_user
from src.config.settings import get_settings
from src.db.engine import get_db
from src.db.models import User
from src.ingest import repository
from src.ingest.extract import IngestValidationError, mime_for_filename, validate_upload
from src.ingest.quota import QuotaExceeded, enforce_upload_quota
from src.ingest.ssrf import validate_url
from src.ingest.storage import delete_upload, put_upload

# Mounted twice by `api_server`: prefix "/api" keeps today's /api/ingest/* alias;
# "/api/v1" is the canonical surface (R15).
router = APIRouter(
    prefix="/ingest", tags=["ingest"], dependencies=[Depends(verify_csrf)]
)

logger = logging.getLogger(__name__)

MAX_FILES = 20
MAX_BYTES = 20 * 1024 * 1024


class UrlRequest(BaseModel):
    url: str


def _validation_error(detail: str) -> HTTPException:
    return HTTPException(
        status_code=422, detail={"code": "validation_error", "message": detail}
    )


async def _enforce_quota(
    db: AsyncSession, user_id, *, incoming_bytes: int = 0, incoming_files: int = 0
) -> None:
    """The per-user quota gate, mapped onto the uniform 429 + Retry-After."""
    try:
        await enforce_upload_quota(
            db,
            user_id,
            incoming_bytes=incoming_bytes,
            incoming_files=incoming_files,
        )
    except QuotaExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "quota_exceeded",
                "message": "Upload quota exceeded for this month.",
            },
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc


async def _discard_staged(db: AsyncSession, object_keys: list[str]) -> None:
    """Roll back rows + objects when the enqueue is refused.

    Without this a 429 from the per-user job cap would leave the upload stored
    with no job to extract it — a permanent empty row in the FE.
    """
    from sqlalchemy import delete

    from src.db.models import Upload

    try:
        await db.execute(delete(Upload).where(Upload.object_key.in_(object_keys)))
        await db.commit()
    except Exception as exc:  # noqa: BLE001 — never mask the enqueue's refusal
        logger.warning("could not roll back staged upload rows: %s", exc)
    for key in object_keys:
        try:
            await asyncio.to_thread(delete_upload, key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not delete staged object %s: %s", key, exc)


@router.post("/files", status_code=202)
async def ingest_files(
    request: Request,
    files: list[UploadFile] = File(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Validate a batch, store it, and queue one extraction job for the lot."""
    if len(files) > MAX_FILES:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "payload_too_large",
                "message": f"Too many files ({len(files)}) — {MAX_FILES} max per batch",
            },
        )

    staged: list[tuple[uuid.UUID, str, bytes]] = []
    for upload in files:
        name = upload.filename or "untitled"
        data = await upload.read()
        if len(data) > MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail={
                    "code": "payload_too_large",
                    "message": f"{name} is over 20 MB",
                },
            )
        try:
            validate_upload(name, data)
        except IngestValidationError as exc:
            raise _validation_error(exc.detail) from exc
        staged.append((uuid.uuid4(), name, data))

    # Quota is checked before anything is stored (429 + Retry-After).
    await _enforce_quota(
        db,
        user.id,
        incoming_bytes=sum(len(data) for _, _, data in staged),
        incoming_files=len(staged),
    )

    upload_ids: list[str] = []
    filenames: dict[str, str] = {}
    object_keys: list[str] = []
    for upload_id, name, data in staged:
        key = await asyncio.to_thread(put_upload, user.id, upload_id, data)
        object_keys.append(key)
        repository.insert_upload(
            db,
            upload_id=upload_id,
            user_id=user.id,
            object_key=key,
            size=len(data),
            mime=mime_for_filename(name),
            sha256=hashlib.sha256(data).hexdigest(),
        )
        upload_ids.append(str(upload_id))
        filenames[str(upload_id)] = name
    await db.commit()

    try:
        job_id = await enqueue_or_http(
            "extract_upload",
            {
                "user_id": str(user.id),
                "upload_ids": upload_ids,
                "filenames": filenames,
                "correlation_id": getattr(request.state, "correlation_id", None),
            },
        )
    except Exception:
        await _discard_staged(db, object_keys)
        raise
    await audit_record(
        db, "upload", user_id=user.id, target=job_id, ip=client_ip(request)
    )
    return {"job_id": job_id, "status": "queued"}


@router.post("/url", status_code=202)
async def ingest_url(
    request: UrlRequest,
    http_request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """SSRF-check the URL, gate on quota, and queue its fetch + extraction."""
    if not request.url.strip():
        raise _validation_error("url is required")
    try:
        validate_url(request.url)
    except IngestValidationError as exc:
        raise _validation_error(exc.detail) from exc

    # A URL's size is unknown until it is fetched: reserve the fetch cap as the
    # bounded worst case, and one file slot.
    await _enforce_quota(
        db,
        user.id,
        incoming_bytes=get_settings().extract_max_output_bytes,
        incoming_files=1,
    )

    job_id = await enqueue_or_http(
        "extract_upload",
        {
            "user_id": str(user.id),
            "kind": "url",
            "url": request.url,
            "correlation_id": getattr(http_request.state, "correlation_id", None),
        },
    )
    await audit_record(
        db, "upload", user_id=user.id, target=job_id, ip=client_ip(http_request)
    )
    return {"job_id": job_id, "status": "queued"}


def _payload(row) -> dict:
    """One upload's extracted payload (or its pending marker)."""
    if not row.extracted_text:
        return {
            "upload_id": str(row.id),
            "mime_type": row.mime,
            "bytes": row.bytes,
            "sha256": row.sha256,
            "text": None,
        }
    try:
        return {"upload_id": str(row.id), **json.loads(row.extracted_text)}
    except ValueError:
        return {"upload_id": str(row.id), "text": row.extracted_text}


@router.get("/documents")
async def get_documents(
    upload_ids: str = Query(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """The extracted payloads for the caller's uploads (a foreign id is absent)."""
    ids = [part.strip() for part in upload_ids.split(",") if part.strip()]
    rows = await repository.owned_uploads(db, user.id, ids)
    return {"documents": [_payload(row) for row in rows]}
