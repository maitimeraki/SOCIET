from uuid import UUID

from pydantic import BaseModel


class ProvenanceLink(BaseModel):
    """Traceability back to the original source text."""

    doc_id: str
    title: str
    breadcrumb: str
    chunk_id: UUID
