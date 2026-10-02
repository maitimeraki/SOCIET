"""Ingest API tests: extraction shapes, per-file failures, url fetch."""
import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.ingest_api import router


@pytest.fixture
def client():
    # FastAPI >=0.135 requires the app-level AsyncExitStack middleware; a bare
    # router lacks it ("fastapi_middleware_astack not found in request scope").
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _pdf_bytes() -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Steel tariffs reshape the European market.")
    data = doc.tobytes()
    doc.close()
    return data


def _docx_bytes() -> bytes:
    import docx

    document = docx.Document()
    document.add_paragraph("Entry costs dominate the expansion decision.")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


class _FakeResponse:
    def __init__(self, status_code: int = 200, text: str = ""):
        self.status_code = status_code
        self.text = text


def test_pdf_document_shape(client):
    response = client.post(
        "/api/ingest/files",
        files=[("files", ("eu-market.pdf", _pdf_bytes(), "application/pdf"))],
    )
    document = response.json()["documents"][0]
    assert response.status_code == 200
    assert document["source_type"] == "file"
    assert document["pages"] == 1
    assert document["word_count"] > 0
    assert document["title"] == "eu-market.pdf"


def test_docx_document_shape(client):
    response = client.post(
        "/api/ingest/files",
        files=[("files", ("steel-tariffs.docx", _docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))],
    )
    document = response.json()["documents"][0]
    assert document["word_count"] > 0
    assert document["source_type"] == "file"


def test_txt_and_markdown_decode(client):
    response = client.post(
        "/api/ingest/files",
        files=[
            ("files", ("notes.txt", b"plain text notes", "text/plain")),
            ("files", ("brief.md", b"# Brief\n\nmarkdown body", "text/markdown")),
        ],
    )
    assert [d["word_count"] for d in response.json()["documents"]] == [3, 3]


def test_unsupported_file_type_fails_per_file(client):
    response = client.post(
        "/api/ingest/files",
        files=[("files", ("sheet.xlsx", b"binary", "application/vnd.ms-excel"))],
    )
    failure = response.json()["failures"][0]
    assert failure["status_code"] == 415
    assert failure["detail"] == "Unsupported file type (.xlsx)"


def test_empty_document_fails_per_file(client):
    response = client.post(
        "/api/ingest/files",
        files=[("files", ("empty.txt", b"   \n  ", "text/plain"))],
    )
    failure = response.json()["failures"][0]
    assert failure["detail"] == "Empty document — 0 words extracted"


def test_oversize_file_fails_per_file(client):
    response = client.post(
        "/api/ingest/files",
        files=[("files", ("big.txt", b"a" * (20 * 1024 * 1024 + 1), "text/plain"))],
    )
    failure = response.json()["failures"][0]
    assert failure["status_code"] == 413
    assert failure["detail"] == "File is over 20 MB"


def test_too_many_files_rejected(client):
    files = [("files", (f"f{i}.txt", b"text", "text/plain")) for i in range(21)]
    response = client.post("/api/ingest/files", files=files)
    assert response.status_code == 413


def test_mixed_batch_keeps_good_files(client):
    response = client.post(
        "/api/ingest/files",
        files=[
            ("files", ("good.txt", b"readable words here", "text/plain")),
            ("files", ("bad.xlsx", b"binary", "application/vnd.ms-excel")),
        ],
    )
    payload = response.json()
    assert response.status_code == 200
    assert len(payload["documents"]) == 1
    assert len(payload["failures"]) == 1


def test_url_document_shape(client, monkeypatch):
    html = "<html><head><title>Steel report</title></head><body><p>Body text here.</p></body></html>"
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: _FakeResponse(200, html))
    response = client.post("/api/ingest/url", json={"url": "https://example.com/report"})
    document = response.json()["document"]
    assert response.status_code == 200
    assert document["source_type"] == "url"
    assert document["title"] == "Steel report"


def test_url_fetch_failure_is_502(client, monkeypatch):
    import requests

    def _raise(*args, **kwargs):
        raise requests.ConnectionError("dns failure")

    monkeypatch.setattr("requests.get", _raise)
    response = client.post("/api/ingest/url", json={"url": "https://example.com/down"})
    assert response.status_code == 502


def test_url_http_error_is_502_with_code(client, monkeypatch):
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: _FakeResponse(403, ""))
    response = client.post("/api/ingest/url", json={"url": "https://example.com/secret"})
    assert response.json()["detail"] == "Download failed: HTTP 403"


def test_api_server_registers_ingest_routes():
    from src.api.api_server import app

    paths = {route.path for route in app.routes}
    assert "/api/ingest/files" in paths
