"""Azure Blob Storage provider.

``azure-storage-blob`` is lazy-imported — users on R2/S3 don't pay the cost.
"""
from __future__ import annotations

import logging
from typing import Iterator

from serena.cloud_sync.exceptions import ProviderConflictError, ProviderError
from serena.cloud_sync.provider import META_SHA256, META_SIZE, CloudStorageProvider, RemoteObjectMeta
from serena.cloud_sync.settings import AzureSettings

log = logging.getLogger(__name__)


class AzureBlobProvider(CloudStorageProvider):
    """Azure Blob Storage via azure-storage-blob."""

    supports_multipart = True
    supports_conditional_put = True
    supports_object_metadata = True
    supports_server_side_copy = True

    def __init__(self, s: AzureSettings) -> None:
        # Lazy import — keep Azure SDK out of the import graph when users
        # are on R2/S3.
        try:
            from azure.storage.blob import BlobServiceClient
        except ImportError as e:  # pragma: no cover - optional dep
            raise ProviderError(
                "azure-storage-blob not installed; install serena with the "
                "`azure` extra (`uv pip install serena[azure]`)"
            ) from e

        self._container_name = s.container
        account_url = f"https://{s.account_name}.blob.{s.endpoint_suffix}"
        self._service = BlobServiceClient(account_url=account_url, credential=s.account_key)
        self._container = self._service.get_container_client(s.container)

    # ---- primitives -------------------------------------------------------

    def list_objects(self, prefix: str) -> Iterator[RemoteObjectMeta]:
        try:
            for blob in self._container.list_blobs(name_starts_with=prefix, include=["metadata"]):
                meta = dict(blob.metadata or {})
                sha = meta.get(META_SHA256)
                yield RemoteObjectMeta(
                    key=blob.name,
                    size=int(blob.size or 0),
                    sha256=sha,
                    etag=getattr(blob, "etag", None),
                    version_id=getattr(blob, "version_id", None),
                    last_modified=getattr(blob, "last_modified", None),
                    metadata_present=sha is not None,
                    raw_metadata=meta,
                )
        except Exception as e:  # azure.core.exceptions.HttpResponseError
            raise _wrap(e, "list_blobs")

    def head_object(self, key: str) -> RemoteObjectMeta | None:
        try:
            from azure.core.exceptions import ResourceNotFoundError
        except ImportError:  # pragma: no cover
            ResourceNotFoundError = Exception
        try:
            b = self._container.get_blob_client(key)
            props = b.get_blob_properties()
        except ResourceNotFoundError:
            return None
        except Exception as e:
            raise _wrap(e, "get_blob_properties")
        meta = dict(props.metadata or {})
        sha = meta.get(META_SHA256)
        return RemoteObjectMeta(
            key=key,
            size=int(props.size or 0),
            sha256=sha,
            etag=props.etag,
            version_id=getattr(props, "version_id", None),
            last_modified=props.last_modified,
            metadata_present=sha is not None,
            raw_metadata=meta,
        )

    def get_object(self, key: str) -> bytes:
        try:
            b = self._container.get_blob_client(key)
            return b.download_blob().readall()
        except Exception as e:
            raise _wrap(e, "download_blob")

    def iter_object(self, key: str, chunk_size: int = 1024 * 1024):
        try:
            b = self._container.get_blob_client(key)
            stream = b.download_blob()
        except Exception as e:
            raise _wrap(e, "download_blob")
        for chunk in stream.chunks():
            yield chunk

    def put_object(self, key: str, data: bytes, sha256_hex: str,
                   content_type: str = "application/octet-stream") -> None:
        try:
            from azure.storage.blob import ContentSettings
        except ImportError as e:  # pragma: no cover
            raise ProviderError("azure-storage-blob not installed") from e
        try:
            b = self._container.get_blob_client(key)
            b.upload_blob(
                data,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
                metadata={META_SHA256: sha256_hex, META_SIZE: str(len(data))},
            )
        except Exception as e:
            raise _wrap(e, "upload_blob")

    def put_object_if_absent(self, key: str, data: bytes, sha256_hex: str,
                             content_type: str = "application/octet-stream") -> bool:
        try:
            from azure.core.exceptions import ResourceExistsError
            from azure.storage.blob import ContentSettings
        except ImportError as e:  # pragma: no cover
            raise ProviderError("azure-storage-blob not installed") from e
        try:
            b = self._container.get_blob_client(key)
            b.upload_blob(
                data,
                overwrite=False,  # Azure's native "if-absent"
                content_settings=ContentSettings(content_type=content_type),
                metadata={META_SHA256: sha256_hex, META_SIZE: str(len(data))},
            )
            return True
        except ResourceExistsError as e:
            existing = self.head_object(key)
            if existing is not None and existing.sha256 == sha256_hex:
                return False
            raise ProviderConflictError(
                f"blob {key!r} already exists with different content",
                provider_code="BlobAlreadyExists",
            ) from e
        except Exception as e:
            raise _wrap(e, "upload_blob")

    def delete_object(self, key: str) -> None:
        try:
            self._container.get_blob_client(key).delete_blob()
        except Exception as e:
            raise _wrap(e, "delete_blob")

    def close(self) -> None:
        try:
            self._service.close()
        except Exception:
            pass


def _wrap(e: Exception, op: str) -> ProviderError:
    status = getattr(e, "status_code", None) or getattr(e, "response", None)
    retryable = False
    try:
        status_int = int(status) if isinstance(status, (int, str)) and str(status).isdigit() else None
    except Exception:
        status_int = None
    if status_int is not None and 500 <= status_int < 600:
        retryable = True
    return ProviderError(f"Azure {op} failed: {e}", retryable=retryable, provider_code=str(status_int or ""))
