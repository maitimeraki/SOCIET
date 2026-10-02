"""Server-side document extraction for the ingest step.

One job: bytes in, `GlobalInputDocument`-shaped dict out. No graph, no LLM.
Failures raise `ExtractionError` with a user-facing sentence; the API layer
maps them onto the per-file failure cards.
"""
import io
import re
import uuid
from typing import Any, Optional

WORD_RE = re.compile(r"\w+")

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_MD_MIME = "text/markdown"
_TXT_MIME = "text/plain"


class ExtractionError(ValueError):
    def __init__(self, detail: str, status_code: int = 422):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _extension(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot >= 0 else ""


def _document(title: str, text: str, source_type: str, mime_type: str, pages: Optional[int] = None) -> dict[str, Any]:
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
    return _document(filename, data.decode("utf-8", errors="replace"), "file", mime_type)


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


def extract_url(url: str) -> dict[str, Any]:
    """Fetch a URL and return its readable text as a document."""
    import requests
    from bs4 import BeautifulSoup

    try:
        response = requests.get(url, timeout=15, headers={"User-Agent": "SimulationWorld/1.0"})
    except requests.RequestException as exc:
        raise ExtractionError(f"Download failed: {exc}", 502) from exc
    if response.status_code >= 400:
        raise ExtractionError(f"Download failed: HTTP {response.status_code}", 502)
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    title_tag = soup.find("title")
    title = (title_tag.get_text(strip=True) if title_tag else "") or url
    return _document(title, text, "url", "text/html")
