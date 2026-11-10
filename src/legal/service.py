"""Seeded legal-document registry and append-only consent records.

``ensure_documents`` is the write path for the seeds; every read path calls it
first so a fresh database serves the current versions without a deploy step.
It deliberately does not commit unless asked: the signup route (Task 10) shares
one transaction between the account row and the consent rows.
"""

import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import LegalDocument, UserConsent
from src.legal import registry


def _effective_datetime(seed: registry.LegalDocSeed) -> datetime.datetime:
    return datetime.datetime.combine(
        seed.effective_at, datetime.time.min, tzinfo=datetime.UTC
    )


async def ensure_documents(
    db: AsyncSession, *, commit: bool = False
) -> list[LegalDocument]:
    """Insert any missing seeds; refuse if committed bytes changed in place.

    ``(slug, version)`` is the immutable identity. A row whose stored hash no
    longer matches the file means the file was edited without a version bump,
    which would make the hash meaningless — so this raises instead of updating.
    """
    rows: list[LegalDocument] = []
    for seed in registry.SEEDS:
        digest = registry.content_sha256(seed)
        # Insert-or-ignore: two concurrent first reads of an empty table must
        # not race a unique violation. The re-select below is the authority.
        await db.execute(
            pg_insert(LegalDocument)
            .values(
                slug=seed.slug,
                version=seed.version,
                effective_at=_effective_datetime(seed),
                content_sha256=digest,
                content=registry.read_raw(seed),
            )
            .on_conflict_do_nothing(index_elements=["slug", "version"])
        )
        row = (
            await db.execute(
                select(LegalDocument).where(
                    LegalDocument.slug == seed.slug,
                    LegalDocument.version == seed.version,
                )
            )
        ).scalar_one()

        if row.content_sha256 != digest:
            raise RuntimeError(
                f"legal document {seed.slug} v{seed.version} changed "
                "without a version bump"
            )
        rows.append(row)

    await db.flush()
    if commit:
        await db.commit()
    return rows


async def current_documents(db: AsyncSession) -> list[LegalDocument]:
    """One row per slug — the highest version — ordered by slug."""
    result = await db.execute(
        select(LegalDocument)
        .distinct(LegalDocument.slug)
        .order_by(LegalDocument.slug, LegalDocument.version.desc())
    )
    return list(result.scalars().all())


async def get_document(db: AsyncSession, slug: str) -> tuple[LegalDocument, str] | None:
    """The current row for ``slug`` and its rendered content, or None.

    Commits the seed check so a read-only detail request does not leave the
    insert transaction open (and re-insert on every request).
    """
    await ensure_documents(db, commit=True)
    row = (
        await db.execute(
            select(LegalDocument)
            .where(LegalDocument.slug == slug)
            .order_by(LegalDocument.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return row, registry.render(row.content)


async def record_consents(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    ip: str | None = None,
    user_agent: str | None = None,
    commit: bool = False,
) -> list[str]:
    """Append an acceptance of each required current document; return the slugs.

    Idempotent per ``(user, document)``: a repeated acceptance is a no-op, never
    an update. ``commit=False`` lets the caller keep the signup transaction.
    """
    await ensure_documents(db)
    current = {row.slug: row for row in await current_documents(db)}

    accepted: list[str] = []
    for slug in registry.REQUIRED_CONSENT_SLUGS:
        document = current[slug]
        await db.execute(
            pg_insert(UserConsent)
            .values(
                user_id=user_id,
                document_id=document.id,
                ip=ip,
                user_agent=user_agent,
            )
            .on_conflict_do_nothing(index_elements=["user_id", "document_id"])
        )
        accepted.append(slug)

    await db.flush()
    if commit:
        await db.commit()
    return accepted


async def has_accepted_current(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """True only when the user accepted every required *current* version."""
    await ensure_documents(db)
    current = {row.slug: row for row in await current_documents(db)}

    for slug in registry.REQUIRED_CONSENT_SLUGS:
        document = current.get(slug)
        if document is None:
            return False
        consent_id = (
            await db.execute(
                select(UserConsent.id)
                .where(
                    UserConsent.user_id == user_id,
                    UserConsent.document_id == document.id,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if consent_id is None:
            return False
    return True
