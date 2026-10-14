"""S3-compatible object storage for uploads (MinIO in dev, plan §7).

Uploads never touch the API container's disk: the request body goes straight
to the bucket. The client is built lazily and cached, so importing this module
— and application startup — never requires S3 to be reachable; the first real
storage call is what fails when the endpoint is down.
"""

from functools import lru_cache
from typing import IO

import boto3

from src.config.settings import get_settings


@lru_cache
def _client():
    """Cached boto3 S3 client for the configured endpoint (lazy, never at import)."""
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )


def upload_key(user_id: object, upload_id: object) -> str:
    """The canonical object key for one upload: ``<user_id>/<upload_id>``."""
    return f"{user_id}/{upload_id}"


def put_upload(user_id: object, upload_id: object, data: bytes) -> str:
    """Store ``data`` under ``user_id/upload_id``; return the object key."""
    key = upload_key(user_id, upload_id)
    _client().put_object(Bucket=get_settings().s3_bucket, Key=key, Body=data)
    return key


def get_upload(key: str) -> IO[bytes]:
    """Return a readable byte stream for ``key`` (caller closes it)."""
    return _client().get_object(Bucket=get_settings().s3_bucket, Key=key)["Body"]


def delete_upload(key: str) -> None:
    """Remove one object — the rollback when an enqueue is refused."""
    _client().delete_object(Bucket=get_settings().s3_bucket, Key=key)
