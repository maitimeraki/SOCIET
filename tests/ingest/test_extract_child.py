"""The extraction child answers the parent with a fixed detail; the raw exception stays in the child's log."""
import base64

from src.ingest import _extract_child

SECRET = "SECRET-EXTRACT-TEXT-9e2b"


def test_an_unexpected_extraction_failure_returns_a_fixed_detail(monkeypatch):
    def boom(filename, data):
        raise RuntimeError(SECRET)

    monkeypatch.setattr("src.ingest.extract.extract_document", boom)
    response = _extract_child._extract(
        {"kind": "file", "filename": "a.pdf", "data": base64.b64encode(b"x").decode()}
    )

    assert response == {"ok": False, "detail": "extraction failed"}
