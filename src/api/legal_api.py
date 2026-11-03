"""Legal document and consent HTTP surface (v1-only, plan §7).

The two GET routes are public: a prospective user must be able to read the
terms and privacy policy before signing up. Consent is a state-changing user
action, so it carries the double-submit CSRF dependency. No content lives in
this module — every read goes through ``src.legal.service``.
"""

import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.audit import client_ip
from src.auth.cookies import verify_csrf
from src.auth.deps import current_user
from src.db.engine import get_db
from src.db.models import LegalDocument, User
from src.legal.service import (
    current_documents,
    ensure_documents,
    get_document,
    record_consents,
)

router = APIRouter(prefix="/api/v1/legal", tags=["legal"])


class LegalDocumentOut(BaseModel):
    slug: str
    version: str
    effective_at: datetime.date
    content_sha256: str


class LegalDocumentDetailOut(LegalDocumentOut):
    content: str


def _metadata(row: LegalDocument) -> LegalDocumentOut:
    return LegalDocumentOut(
        slug=row.slug,
        version=row.version,
        effective_at=row.effective_at.date(),
        content_sha256=row.content_sha256,
    )


@router.get("/documents", response_model=list[LegalDocumentOut])
async def list_documents(
    db: AsyncSession = Depends(get_db),
) -> list[LegalDocumentOut]:
    """The current version of every published document."""
    await ensure_documents(db, commit=True)
    return [_metadata(row) for row in await current_documents(db)]


@router.get("/documents/{slug}", response_model=LegalDocumentDetailOut)
async def document_detail(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> LegalDocumentDetailOut:
    """One document's metadata plus its rendered content."""
    found = await get_document(db, slug)
    if found is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "Legal document not found."},
        )
    row, content = found
    return LegalDocumentDetailOut(**_metadata(row).model_dump(), content=content)


@router.post("/consent", dependencies=[Depends(verify_csrf)])
async def give_consent(
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Record the session user's acceptance of every required current version."""
    accepted = await record_consents(
        db,
        user_id=user.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        commit=True,
    )
    return {"accepted": accepted}
