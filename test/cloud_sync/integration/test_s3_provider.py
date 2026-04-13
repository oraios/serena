"""LocalStack-backed round-trip for the S3 / R2 providers.

Skipped unless ``LOCALSTACK_ENDPOINT`` is set in the environment. Works against
any S3-compatible backend exposed at that endpoint (tested with LocalStack and
MinIO).
"""
from __future__ import annotations

import os

import pytest

from serena.cloud_sync.exceptions import ProviderConflictError
from serena.cloud_sync.settings import S3Settings

pytestmark = pytest.mark.skipif(
    not os.environ.get("LOCALSTACK_ENDPOINT"),
    reason="set LOCALSTACK_ENDPOINT=http://localhost:4566 (or your MinIO URL) to run",
)


@pytest.fixture
def s3_provider():
    from serena.cloud_sync.providers.s3 import S3Provider
    settings = S3Settings(
        access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
        secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
        bucket=os.environ.get("S3_BUCKET", "serena-cloud-sync-test"),
        region=os.environ.get("AWS_REGION", "us-east-1"),
        endpoint_url=os.environ["LOCALSTACK_ENDPOINT"],
    )
    provider = S3Provider(settings)
    # Ensure bucket exists (LocalStack allows creation without auth fanfare)
    try:
        provider._client.create_bucket(Bucket=settings.bucket)
    except Exception:
        pass
    yield provider
    provider.close()


def test_roundtrip(s3_provider) -> None:
    key = "serena-test/roundtrip.md"
    body = b"hello serena" * 10
    import hashlib
    sha = hashlib.sha256(body).hexdigest()

    assert s3_provider.put_object_if_absent(key, body, sha) is True
    # Idempotent: same content returns False
    assert s3_provider.put_object_if_absent(key, body, sha) is False
    assert s3_provider.get_object(key) == body
    meta = s3_provider.head_object(key)
    assert meta is not None
    assert meta.sha256 == sha
    s3_provider.delete_object(key)
    assert s3_provider.head_object(key) is None


def test_conflict(s3_provider) -> None:
    key = "serena-test/conflict.md"
    import hashlib
    s3_provider.put_object_if_absent(key, b"A", hashlib.sha256(b"A").hexdigest())
    with pytest.raises(ProviderConflictError):
        s3_provider.put_object_if_absent(key, b"B", hashlib.sha256(b"B").hexdigest())
    s3_provider.delete_object(key)
