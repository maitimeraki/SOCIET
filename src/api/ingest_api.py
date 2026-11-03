"""Ingest API: accept uploads and hand extraction to the worker (R17).

Both routes validate at the trust boundary and *enqueue* — they never extract:
``POST /files`` magic-byte-checks each upload, reserves a byte ceiling of units,
puts the bytes in the object bucket, writes the ``uploads`` rows, and queues one
``extract_upload`` job; ``POST /url`` runs the SSRF guard, reserves the fetch
cap, and queues the fetch. Both answer ``202 {job_id, status: "queued"}``
(uniform with the debate enqueue). The worker settles the measured characters
and releases the surplus. ``DELETE /uploads/{id}`` removes one owned document.
The extracted payloads are read back through ``GET /documents``.
"""

import asyncio
import datetime
import hashlib
import json
import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.errors import payment_required
from src.api.jobs_api import enqueue_or_http
from src.audit import client_ip
from src.audit import record as audit_record
from src.auth.cookies import verify_csrf
from src.auth.deps import current_user, require_owner
from src.billing import units
from src.billing.units import Reservation
from src.config.settings import get_settings
from src.db.engine import get_db
from src.db.models import Dataset, Upload, User
from src.ingest import repository
from src.ingest.extract import IngestValidationError, mime_for_filename, validate_upload
from src.ingest.ssrf import validate_url
from src.ingest.storage import delete_upload, put_upload

# Mounted twice by `api_server`: prefix "/api" keeps today's /api/ingest/* alias;
# "/api/v1" is the canonical surface (R15). The router is prefix-less: each
# route's own path is the whole surface — the ingest trio carries "/ingest" and
# the documents list carries "/uploads" (so it lands at /api/v1/uploads).
router = APIRouter(tags=["ingest"], dependencies=[Depends(verify_csrf)])

logger = logging.getLogger(__name__)

MAX_FILES = 20
MAX_BYTES = 20 * 1024 * 1024


class UrlRequest(BaseModel):
    url: str


def _validation_error(detail: str) -> HTTPException:
    return HTTPException(
        status_code=422, detail={"code": "validation_error", "message": detail}
    )


async def _reserve_ingest(
    db: AsyncSession, *, user, estimate: int, request
) -> Reservation:
    """Reserve the upload's byte ceiling; an exhausted balance is a 402."""
    try:
        reservation = await units.reserve_units(
            db, user_id=user.id, plan_key=user.plan_key, estimate=max(1, estimate)
        )
    except units.InsufficientUnits as exc:
        await audit_record(
            db,
            "units_denied",
            user_id=user.id,
            ip=client_ip(request),
            meta={"estimate": estimate, "period_end": exc.period_end.isoformat()},
        )
        raise payment_required(
            f"Units used up. They reset on {exc.period_end.date().isoformat()}."
        ) from exc
    await audit_record(
        db,
        "units_reserve",
        user_id=user.id,
        ip=client_ip(request),
        meta={"estimate": estimate, "source": "ingest"},
    )
    return reservation


async def _discard_staged(db: AsyncSession, object_keys: list[str]) -> None:
    """Roll back rows + objects when the enqueue is refused.

    Without this a 429 from the per-user job cap would leave the upload stored
    with no job to extract it — a permanent empty row in the FE.
    """
    from sqlalchemy import delete

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


@router.post("/ingest/files", status_code=202)
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

    # The reservation is a conservative ceiling (bytes >= extracted chars), so
    # it is taken before anything is stored; the worker settles the measured
    # character count and releases the surplus.
    cap = get_settings().extract_max_output_bytes
    estimate = sum(
        max(1, units.units_for_chars(min(len(data), cap))) for _, _, data in staged
    )
    reservation = await _reserve_ingest(
        db, user=user, estimate=estimate, request=request
    )

    upload_ids: list[str] = []
    filenames: dict[str, str] = {}
    object_keys: list[str] = []
    try:
        for upload_id, name, data in staged:
            key = await asyncio.to_thread(put_upload, user.id, upload_id, data)
            object_keys.append(key)
            repository.insert_upload(
                db,
                upload_id=upload_id,
                user_id=user.id,
                object_key=key,
                name=name,
                size=len(data),
                mime=mime_for_filename(name),
                sha256=hashlib.sha256(data).hexdigest(),
            )
            upload_ids.append(str(upload_id))
            filenames[str(upload_id)] = name
        await db.commit()

        job_id = await enqueue_or_http(
            "extract_upload",
            {
                "user_id": str(user.id),
                "upload_ids": upload_ids,
                "filenames": filenames,
                "reserved_units": reservation.amount,
                "reserved_period_start": reservation.period_start.isoformat(),
                "reserved_at": datetime.datetime.now(datetime.UTC).isoformat(),
                "correlation_id": getattr(request.state, "correlation_id", None),
            },
        )
    except Exception:
        await _discard_staged(db, object_keys)
        await units.release_reservation(
            db,
            user_id=user.id,
            period_start=reservation.period_start,
            amount=reservation.amount,
        )
        raise
    await audit_record(
        db, "upload", user_id=user.id, target=job_id, ip=client_ip(request)
    )
    return {"job_id": job_id, "status": "queued"}


@router.post("/ingest/url", status_code=202)
async def ingest_url(
    request: UrlRequest,
    http_request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """SSRF-check the URL, reserve its fetch cap, and queue fetch + extraction."""
    if not request.url.strip():
        raise _validation_error("url is required")
    try:
        validate_url(request.url)
    except IngestValidationError as exc:
        raise _validation_error(exc.detail) from exc

    # A URL's size is unknown until it is fetched: reserve the fetch cap as the
    # bounded worst case.
    reservation = await _reserve_ingest(
        db,
        user=user,
        estimate=max(1, units.units_for_chars(get_settings().extract_max_output_bytes)),
        request=http_request,
    )

    try:
        job_id = await enqueue_or_http(
            "extract_upload",
            {
                "user_id": str(user.id),
                "kind": "url",
                "url": request.url,
                "reserved_units": reservation.amount,
                "reserved_period_start": reservation.period_start.isoformat(),
                "reserved_at": datetime.datetime.now(datetime.UTC).isoformat(),
                "correlation_id": getattr(http_request.state, "correlation_id", None),
            },
        )
    except Exception:
        await units.release_reservation(
            db,
            user_id=user.id,
            period_start=reservation.period_start,
            amount=reservation.amount,
        )
        raise
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


@router.get("/ingest/documents")
async def get_documents(
    upload_ids: str = Query(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """The extracted payloads for the caller's uploads (a foreign id is absent)."""
    ids = [part.strip() for part in upload_ids.split(",") if part.strip()]
    rows = await repository.owned_uploads(db, user.id, ids)
    return {"documents": [_payload(row) for row in rows]}


@router.get("/uploads")
async def list_uploads(
    limit: int = Query(100, ge=1),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """The caller's own uploads, newest first — the documents section's rows.

    Every field comes off the row: ``name`` is the stored upload name (the
    filename as supplied at ingest — never the object key), ``read`` is
    ``extracted_text is not None``, and ``dataset_name`` is left-joined from
    ``Dataset`` (null until the upload joins a corpus). Scoped to the caller,
    never a filter a request can drop.
    """
    rows = await db.execute(
        select(Upload, Dataset.name)
        .join(Dataset, Upload.dataset_id == Dataset.id, isouter=True)
        .where(Upload.user_id == user.id)
        .order_by(Upload.created_at.desc())
        .limit(min(limit, 200))
    )
    return {
        "items": [
            {
                "id": str(upload.id),
                "name": upload.name,
                "bytes": upload.bytes,
                "mime": upload.mime,
                "read": upload.extracted_text is not None,
                "dataset_id": str(upload.dataset_id) if upload.dataset_id else None,
                "dataset_name": dataset_name,
                "created_at": upload.created_at.isoformat(),
            }
            for upload, dataset_name in rows.all()
        ]
    }


@router.delete("/uploads/{upload_id}", status_code=204)
async def delete_upload_route(
    upload_id: uuid.UUID,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete one owned document — the row and (for a stored file) its object.

    A missing row and a foreign row are both 404: existence is not leaked. A URL
    upload keeps its source URL in ``object_key``, so only keys under the
    caller's ``<user_id>/`` prefix reach S3.
    """
    row = await repository.get_upload_row(db, upload_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "Not found."}
        )
    await require_owner(row.user_id, user)

    object_key = row.object_key
    await db.delete(row)
    await db.commit()
    if object_key.startswith(f"{user.id}/"):
        await asyncio.to_thread(delete_upload, object_key)
    await audit_record(
        db,
        "upload_delete",
        user_id=user.id,
        target=str(upload_id),
        ip=client_ip(request),
    )
