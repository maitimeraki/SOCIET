"""Ingest API: upload documents and fetch URLs into GlobalInputDocument payloads."""
import asyncio

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from src.ingest.extract import ExtractionError, extract_document, extract_url

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

MAX_FILES = 20
MAX_BYTES = 20 * 1024 * 1024


class UrlRequest(BaseModel):
    url: str


@router.post("/files")
async def ingest_files(files: list[UploadFile] = File(...)):
    """Extract one batch of uploads. Per-file failures ride beside the documents."""
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=413, detail=f"Too many files ({len(files)}) — {MAX_FILES} max per batch")

    documents: list[dict] = []
    failures: list[dict] = []
    for upload in files:
        name = upload.filename or "untitled"
        data = await upload.read()
        if len(data) > MAX_BYTES:
            failures.append({"filename": name, "status_code": 413, "detail": "File is over 20 MB"})
            continue
        try:
            documents.append(await asyncio.to_thread(extract_document, name, data))
        except ExtractionError as exc:
            failures.append({"filename": name, "status_code": exc.status_code, "detail": exc.detail})
    return {"documents": documents, "failures": failures}


@router.post("/url")
async def ingest_url(request: UrlRequest):
    if not request.url.strip():
        raise HTTPException(status_code=422, detail="url is required")
    try:
        document = await asyncio.to_thread(extract_url, request.url)
    except ExtractionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    return {"document": document}
