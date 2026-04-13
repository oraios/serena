"""Shared S3-compatible provider implementation (boto3).

Used directly by AWS S3 and subclassed by R2 with an ``endpoint_url`` override.
Can also be used for any S3-compatible backend (MinIO, Ceph RGW, SeaweedFS).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterator

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from serena.cloud_sync.exceptions import ProviderConflictError, ProviderError
from serena.cloud_sync.provider import META_SHA256, META_SIZE, CloudStorageProvider, RemoteObjectMeta

log = logging.getLogger(__name__)


class BaseS3Provider(CloudStorageProvider):
    """S3-compatible provider via boto3.

    Subclasses typically only override the constructor to set ``endpoint_url``
    and region defaults (see ``r2.py``, ``s3.py``).
    """

    supports_multipart = True
    supports_conditional_put = True
    supports_object_metadata = True
    supports_server_side_copy = True

    def __init__(
        self,
        *,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        region: str = "us-east-1",
        endpoint_url: str | None = None,
        signature_version: str = "s3v4",
    ) -> None:
        self._bucket = bucket
        cfg = BotoConfig(
            signature_version=signature_version,
            retries={"max_attempts": 5, "mode": "standard"},
            s3={"addressing_style": "path"},
        )
        self._client = boto3.client(
            "s3",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
            endpoint_url=endpoint_url,
            config=cfg,
        )

    # ---- primitives -------------------------------------------------------

    def list_objects(self, prefix: str) -> Iterator[RemoteObjectMeta]:
        paginator = self._client.get_paginator("list_objects_v2")
        try:
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    # HEAD is needed for metadata; defer it and do HEAD per-key when
                    # diff needs sha256. This lets quick status queries be cheap.
                    yield RemoteObjectMeta(
                        key=obj["Key"],
                        size=int(obj.get("Size", 0)),
                        etag=(obj.get("ETag") or "").strip('"') or None,
                        last_modified=obj.get("LastModified"),
                        metadata_present=False,  # set after HEAD
                    )
        except ClientError as e:
            raise _wrap(e, "list_objects_v2")

    def head_object(self, key: str) -> RemoteObjectMeta | None:
        try:
            res = self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as e:
            code = _err_code(e)
            if code in ("404", "NoSuchKey", "NotFound"):
                return None
            raise _wrap(e, "head_object")
        meta = res.get("Metadata") or {}
        sha = meta.get(META_SHA256)
        size = int(res.get("ContentLength") or 0)
        return RemoteObjectMeta(
            key=key,
            size=size,
            sha256=sha,
            etag=(res.get("ETag") or "").strip('"') or None,
            version_id=res.get("VersionId"),
            last_modified=res.get("LastModified"),
            metadata_present=sha is not None,
            raw_metadata=meta,
        )

    def get_object(self, key: str) -> bytes:
        try:
            res = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as e:
            raise _wrap(e, "get_object")
        return res["Body"].read()

    def iter_object(self, key: str, chunk_size: int = 1024 * 1024):
        try:
            res = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as e:
            raise _wrap(e, "get_object")
        body = res["Body"]
        while True:
            chunk = body.read(chunk_size)
            if not chunk:
                return
            yield chunk

    def put_object(self, key: str, data: bytes, sha256_hex: str,
                   content_type: str = "application/octet-stream") -> None:
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                Metadata={META_SHA256: sha256_hex, META_SIZE: str(len(data))},
            )
        except ClientError as e:
            raise _wrap(e, "put_object")

    def put_object_if_absent(self, key: str, data: bytes, sha256_hex: str,
                             content_type: str = "application/octet-stream") -> bool:
        """Atomic conditional upload using ``If-None-Match: *``.

        Most S3-compatible backends (incl. R2) honor this header on PutObject.
        For backends that don't, the sync layer's fallback path is:
            HEAD key -> if present return False; else unconditional PUT.
        This fallback races, which is exactly why we prefer conditional put.
        """
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                Metadata={META_SHA256: sha256_hex, META_SIZE: str(len(data))},
                IfNoneMatch="*",
            )
            return True
        except ClientError as e:
            code = _err_code(e)
            if code in ("412", "PreconditionFailed"):
                # Key already exists. Classify by content: if sha256 on remote
                # equals ours, it's a no-op (SKIP); otherwise CONFLICT.
                existing = self.head_object(key)
                if existing is not None and existing.sha256 == sha256_hex:
                    return False
                raise ProviderConflictError(
                    f"object {key!r} already exists with different content",
                    provider_code="412",
                ) from e
            # Some providers (older MinIO) don't support IfNoneMatch and
            # return 501 / 400. Fall back to HEAD-then-PUT.
            if code in ("NotImplemented", "501", "InvalidArgument", "400"):
                log.warning(
                    "provider does not support If-None-Match; falling back to HEAD-then-PUT (race window)"
                )
                if self.head_object(key) is not None:
                    return False
                self.put_object(key, data, sha256_hex, content_type)
                return True
            raise _wrap(e, "put_object_if_absent")

    def delete_object(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except ClientError as e:
            raise _wrap(e, "delete_object")

    def close(self) -> None:
        # boto3 clients manage their own pool; nothing to close explicitly.
        return None


def _err_code(e: ClientError) -> str:
    return str(e.response.get("Error", {}).get("Code", ""))


def _wrap(e: ClientError, op: str) -> ProviderError:
    code = _err_code(e)
    # Retryable on 5xx and throttling codes
    retryable = code in {"500", "502", "503", "504", "SlowDown", "RequestTimeout"}
    return ProviderError(f"S3 {op} failed: {code}", retryable=retryable, provider_code=code)
