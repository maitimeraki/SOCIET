"""Magic-byte validation: accept matrix per format, reject spoofed files."""

import pytest

from src.ingest.extract import (
    ExtractionError,
    IngestValidationError,
    sniff_kind,
    validate_upload,
)

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
DOCX_BYTES = b"PK\x03\x04" + b"\x14\x00\x06\x00\x00\x00" + b"\x00" * 16
TEXT_BYTES = b"# Brief\n\nSteel tariffs reshape the European market.\n"


@pytest.mark.parametrize(
    ("filename", "data", "kind"),
    [
        ("report.pdf", PDF_BYTES, "pdf"),
        ("report.docx", DOCX_BYTES, "docx"),
        ("notes.txt", TEXT_BYTES, "text"),
        ("brief.md", TEXT_BYTES, "text"),
        ("brief.markdown", TEXT_BYTES, "text"),
    ],
)
def test_accept_matrix(filename, data, kind):
    assert validate_upload(filename, data) == kind


@pytest.mark.parametrize(
    ("filename", "data"),
    [
        ("sheet.xlsx", b"PK\x03\x04junk"),  # outside the allowlist
        ("image.png", b"\x89PNG\r\n\x1a\n"),
        ("archive.zip", b"PK\x03\x04junk"),
        ("noext", TEXT_BYTES),
    ],
)
def test_reject_not_in_allowlist(filename, data):
    with pytest.raises(IngestValidationError, match="Unsupported file type"):
        validate_upload(filename, data)


@pytest.mark.parametrize(
    ("filename", "data"),
    [
        ("fake.pdf", TEXT_BYTES),  # text renamed .pdf
        ("fake.pdf", DOCX_BYTES),  # zip renamed .pdf
        ("fake.docx", PDF_BYTES),  # pdf renamed .docx
        ("fake.docx", TEXT_BYTES),  # text renamed .docx
        ("fake.txt", PDF_BYTES),  # pdf renamed .txt
        ("fake.md", DOCX_BYTES),  # zip renamed .md
        ("binary.txt", b"\x00\x01\x02\x03binary"),  # NUL bytes -> not text
    ],
)
def test_reject_extension_spoofed(filename, data):
    with pytest.raises(IngestValidationError, match="do not match"):
        validate_upload(filename, data)


def test_sniff_kind_classifies_by_content():
    assert sniff_kind(PDF_BYTES) == "pdf"
    assert sniff_kind(DOCX_BYTES) == "docx"
    assert sniff_kind(TEXT_BYTES) == "text"
    assert sniff_kind(b"\x00\xff\xfe binary") == "unknown"


def test_validation_error_is_422_mappable():
    # 9c maps this onto the uniform 422 contract; it carries a readable message.
    with pytest.raises(IngestValidationError) as caught:
        validate_upload("fake.pdf", TEXT_BYTES)
    assert isinstance(caught.value, ExtractionError)
    assert caught.value.status_code == 422
    assert str(caught.value) == "File contents do not match the .pdf extension"
