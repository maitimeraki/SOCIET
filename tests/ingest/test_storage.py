"""Object storage: put/get round-trips through a mocked S3 (moto)."""

from types import SimpleNamespace

import pytest

from src.ingest import storage

BUCKET = "societas-uploads"


@pytest.fixture
def s3(monkeypatch):
    """A mocked S3 with the configured bucket; a fresh client per test.

    moto only intercepts the default AWS endpoint, not a custom MinIO URL, so
    the client is pointed at the default endpoint for the duration of the test.
    """
    moto = pytest.importorskip("moto")
    settings = SimpleNamespace(
        s3_endpoint_url=None,
        s3_access_key="testing",
        s3_secret_key="testing",
        s3_bucket=BUCKET,
        s3_region="us-east-1",
    )
    monkeypatch.setattr(storage, "get_settings", lambda: settings)
    with moto.mock_aws():
        storage._client.cache_clear()
        storage._client().create_bucket(Bucket=BUCKET)
        yield
    storage._client.cache_clear()


def test_put_upload_returns_canonical_key(s3):
    assert storage.put_upload("user-1", "upload-9", b"hello") == "user-1/upload-9"


def test_round_trip_returns_stored_bytes(s3):
    data = b"%PDF-1.7\nfake pdf body\n%%EOF\n"
    key = storage.put_upload("user-1", "upload-9", data)
    with storage.get_upload(key) as body:
        assert body.read() == data


def test_distinct_uploads_do_not_collide(s3):
    storage.put_upload("user-1", "a", b"first")
    storage.put_upload("user-1", "b", b"second")
    with storage.get_upload("user-1/b") as body:
        assert body.read() == b"second"
