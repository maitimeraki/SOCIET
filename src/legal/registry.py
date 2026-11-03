"""The immutable legal-document registry: seeds, raw content, hashes, rendering.

One seed per published document version. A content change must ship with a new
``version`` — ``src.legal.service.ensure_documents`` refuses to run otherwise.
"""

import datetime
import hashlib
from dataclasses import dataclass
from pathlib import Path

from src.config.settings import get_settings

CONTENT_DIR = Path(__file__).parent / "content"

#: Placeholders substituted at render time; the files keep the raw tokens.
ENTITY_PLACEHOLDER = "{{legal_entity_name}}"
CONTACT_PLACEHOLDER = "{{legal_contact_email}}"
FALLBACK_ENTITY = "Societas"
FALLBACK_CONTACT = "hello@societas.app"


@dataclass(frozen=True)
class LegalDocSeed:
    slug: str
    version: str  # ISO date string, e.g. "2026-11-03"
    effective_at: datetime.date
    filename: str


REQUIRED_CONSENT_SLUGS = ("terms", "privacy")

_VERSION = "2026-11-03"
_EFFECTIVE_AT = datetime.date(2026, 11, 3)

SEEDS: tuple[LegalDocSeed, ...] = (
    LegalDocSeed("terms", _VERSION, _EFFECTIVE_AT, "terms.md"),
    LegalDocSeed("privacy", _VERSION, _EFFECTIVE_AT, "privacy.md"),
    LegalDocSeed("refund", _VERSION, _EFFECTIVE_AT, "refund.md"),
    LegalDocSeed("subprocessors", _VERSION, _EFFECTIVE_AT, "subprocessors.md"),
)


def read_raw(seed: LegalDocSeed) -> str:
    """The document bytes as text, exactly as committed."""
    return (CONTENT_DIR / seed.filename).read_text(encoding="utf-8")


def content_sha256(seed: LegalDocSeed) -> str:
    """SHA-256 of the document's UTF-8 bytes."""
    return hashlib.sha256(read_raw(seed).encode("utf-8")).hexdigest()


def render(raw: str) -> str:
    """Substitute the entity and contact placeholders.

    An unset ``LEGAL_ENTITY_NAME`` renders the honest fallback "Societas"; an
    unset ``LEGAL_CONTACT_EMAIL`` renders the default contact address.
    """
    settings = get_settings()
    entity = settings.legal_entity_name.strip() or FALLBACK_ENTITY
    email = settings.legal_contact_email.strip() or FALLBACK_CONTACT
    return raw.replace(ENTITY_PLACEHOLDER, entity).replace(CONTACT_PLACEHOLDER, email)


def seed_for(slug: str) -> LegalDocSeed | None:
    for seed in SEEDS:
        if seed.slug == slug:
            return seed
    return None
