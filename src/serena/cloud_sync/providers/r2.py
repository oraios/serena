"""Cloudflare R2 provider.

R2 is S3-compatible via an ``endpoint_url`` override; R2 uses region ``auto``
and rejects some AWS-specific signing extensions.
"""
from __future__ import annotations

from serena.cloud_sync.providers.base_s3 import BaseS3Provider
from serena.cloud_sync.settings import R2Settings


class R2Provider(BaseS3Provider):
    """Cloudflare R2 via boto3."""

    def __init__(self, s: R2Settings) -> None:
        super().__init__(
            bucket=s.bucket,
            access_key_id=s.access_key_id,
            secret_access_key=s.secret_access_key,
            region="auto",
            endpoint_url=s.resolved_endpoint(),
        )
