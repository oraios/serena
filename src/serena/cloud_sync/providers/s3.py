"""Amazon S3 (and S3-compatible) provider.

The ``endpoint_url`` field is optional; when set, it enables MinIO / Ceph RGW /
SeaweedFS / LocalStack targets using the same protocol surface.
"""
from __future__ import annotations

from serena.cloud_sync.providers.base_s3 import BaseS3Provider
from serena.cloud_sync.settings import S3Settings


class S3Provider(BaseS3Provider):
    """Amazon S3 (or any S3-compatible backend)."""

    def __init__(self, s: S3Settings) -> None:
        super().__init__(
            bucket=s.bucket,
            access_key_id=s.access_key_id,
            secret_access_key=s.secret_access_key,
            region=s.region,
            endpoint_url=s.resolved_endpoint(),
        )
