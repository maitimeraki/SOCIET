"""Server-side document extraction for the ingest step.

One job: bytes in, `GlobalInputDocument`-shaped dict out. No graph, no LLM.
Failures raise `ExtractionError` with a user-facing sentence; the extraction
worker maps them onto a readable job failure (``src.jobs.tasks``), and
``validate_upload`` raises `IngestValidationError` that the route maps onto the
uniform 422 contract before anything is stored.
"""

import hashlib
import io
import re
import uuid
from typing import Any, Optional

WORD_RE = re.compile(r"\w+")

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_MD_MIME = "text/markdown"
_TXT_MIME = "text/plain"
_HTML_MIME = "text/html"


class ExtractionError(ValueError):
    def __init__(self, detail: str, status_code: int = 422):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class IngestValidationError(ExtractionError):
    """An upload that fails format validation (mismatched or spoofed type).

    Distinct from `ExtractionError` so the route layer can map it onto the
    uniform 422 contract *before* any storage or extraction happens.
    """


def _extension(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot >= 0 else ""


# The stored mime is derived from the (already magic-byte-validated) extension,
# never from the client's Content-Type header.
_MIME_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".docx": _DOCX_MIME,
    ".md": _MD_MIME,
    ".markdown": _MD_MIME,
    ".txt": _TXT_MIME,
}


def mime_for_filename(filename: str) -> str:
    """The canonical mime for an allowlisted extension (else octet-stream)."""
    return _MIME_BY_EXTENSION.get(_extension(filename), "application/octet-stream")


# The extension is only a hint: `validate_upload` confirms the bytes match it.
_KIND_BY_EXTENSION = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".md": "text",
    ".markdown": "text",
    ".txt": "text",
}
_TEXT_SAMPLE_BYTES = 8192


def _looks_like_text(data: bytes) -> bool:
    """UTF-8/ASCII heuristic over the sampled head: decodes and has no NUL."""
    sample = data[:_TEXT_SAMPLE_BYTES]
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def sniff_kind(data: bytes) -> str:
    """Classify bytes by content: 'pdf', 'docx', 'text', or 'unknown'."""
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:4] == b"PK\x03\x04":  # zip container (docx)
        return "docx"
    if _looks_like_text(data):
        return "text"
    return "unknown"


def validate_upload(filename: str, data: bytes) -> str:
    """Validate one upload's bytes against its extension; return the kind.

    Raises `IngestValidationError` when the extension is outside the allowlist
    or the content does not match it (a PDF renamed .txt is rejected, and so
    on). Pure stdlib — no libmagic.
    """
    extension = _extension(filename)
    expected = _KIND_BY_EXTENSION.get(extension)
    if expected is None:
        raise IngestValidationError(f"Unsupported file type ({extension or filename})")
    kind = sniff_kind(data)
    if kind != expected:
        raise IngestValidationError(
            f"File contents do not match the {extension} extension"
        )
    return kind


def _document(
    title: str, text: str, source_type: str, mime_type: str, pages: Optional[int] = None
) -> dict[str, Any]:
    word_count = len(WORD_RE.findall(text))
    if word_count == 0:
        raise ExtractionError("Empty document — 0 words extracted")
    document: dict[str, Any] = {
        "document_id": uuid.uuid4().hex,
        "title": title,
        "text": text,
        "word_count": word_count,
        "source_type": source_type,
        "mime_type": mime_type,
    }
    if pages is not None:
        document["pages"] = pages
    return document


def extract_pdf(filename: str, data: bytes) -> dict[str, Any]:
    import fitz  # PyMuPDF

    try:
        with fitz.open(stream=data, filetype="pdf") as pdf:
            text = "\n".join(page.get_text() for page in pdf)
            pages = pdf.page_count
    except Exception as exc:
        raise ExtractionError("not a readable document") from exc
    return _document(filename, text, "file", "application/pdf", pages)


def extract_docx(filename: str, data: bytes) -> dict[str, Any]:
    import docx  # python-docx

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise ExtractionError("not a readable document") from exc
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    return _document(filename, text, "file", _DOCX_MIME)


def extract_plain(filename: str, data: bytes, mime_type: str) -> dict[str, Any]:
    return _document(
        filename, data.decode("utf-8", errors="replace"), "file", mime_type
    )


def extract_document(filename: str, data: bytes) -> dict[str, Any]:
    """Extract one uploaded file. Raises ExtractionError with a user-facing reason."""
    extension = _extension(filename)
    if extension == ".pdf":
        return extract_pdf(filename, data)
    if extension == ".docx":
        return extract_docx(filename, data)
    if extension in (".md", ".markdown"):
        return extract_plain(filename, data, _MD_MIME)
    if extension == ".txt":
        return extract_plain(filename, data, _TXT_MIME)
    raise ExtractionError(f"Unsupported file type ({extension or filename})", 415)


def extract_url(
    url: str, max_bytes: Optional[int] = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fetch a URL through the SSRF guard; return ``(document, meta)``.

    The fetch is the guarded one (``src.ingest.ssrf.fetch_url``): DNS-resolved
    address allowlisting, manual redirects, and a streamed byte cap. ``meta``
    carries the final URL plus the body's byte length and sha256, so the worker
    can record the upload row without re-fetching.
    """
    from bs4 import BeautifulSoup

    from src.ingest.ssrf import fetch_url

    final_url, body = (
        fetch_url(url) if max_bytes is None else fetch_url(url, max_bytes=max_bytes)
    )
    soup = BeautifulSoup(body.decode("utf-8", errors="replace"), "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    title_tag = soup.find("title")
    title = (title_tag.get_text(strip=True) if title_tag else "") or final_url
    document = _document(title, text, "url", _HTML_MIME)
    meta = {
        "source_url": final_url,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }
    return document, meta
