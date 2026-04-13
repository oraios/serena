"""DIP seam for cloud sync.

``CloudStorageProvider`` is the abstract interface. Concrete implementations
live under ``serena.cloud_sync.providers``. The sync service depends on this
interface only — it never imports ``boto3`` or ``azure.storage.blob``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator

META_SHA256 = "serena-sync-sha256"
META_SIZE = "serena-sync-size"


@dataclass(frozen=True)
class RemoteObjectMeta:
    """Provider-neutral description of a remote object."""
    key: str
    size: int
    sha256: str | None = None
    """Populated from x-*-meta-serena-sync-sha256 when present. None for legacy
    objects; stream-hash fallback will fill it at diff time."""

    etag: str | None = None
    version_id: str | None = None
    last_modified: datetime | None = None
    metadata_present: bool = False
    """True when our serena-sync metadata keys are present on the object."""

    raw_metadata: dict[str, str] = field(default_factory=dict)


class CloudStorageProvider(ABC):
    """Abstract cloud storage provider.

    Implementations translate between these primitives and their native SDK.
    The sync layer calls only these methods.
    """

    # ---- capability flags -------------------------------------------------
    supports_multipart: bool = False
    supports_conditional_put: bool = True
    supports_object_metadata: bool = True
    supports_server_side_copy: bool = False

    # ---- primitives -------------------------------------------------------
    @abstractmethod
    def list_objects(self, prefix: str) -> Iterator[RemoteObjectMeta]:
        """Yield every object whose key starts with ``prefix``. Must be
        eager-safe (no infinite pagination loops)."""

    @abstractmethod
    def head_object(self, key: str) -> RemoteObjectMeta | None:
        """Return metadata for ``key``, or None if absent."""

    @abstractmethod
    def get_object(self, key: str) -> bytes:
        """Return the object body. Small files only (MVP cap 5 MiB)."""

    @abstractmethod
    def iter_object(self, key: str, chunk_size: int = 1024 * 1024):
        """Stream the object body in chunks (for byte-by-byte compare)."""

    @abstractmethod
    def put_object(
        self,
        key: str,
        data: bytes,
        sha256_hex: str,
        content_type: str = "application/octet-stream",
    ) -> None:
        """Unconditional upload. Rarely used; ``put_object_if_absent`` is preferred."""

    @abstractmethod
    def put_object_if_absent(
        self,
        key: str,
        data: bytes,
        sha256_hex: str,
        content_type: str = "application/octet-stream",
    ) -> bool:
        """Conditional upload: succeed only if no object exists at ``key``.

        Return True if written, False if a prior object exists. On content
        conflict (412 on a provider that returns Precondition Failed), raise
        ``ProviderConflictError`` so the sync layer classifies it as CONFLICT.
        """

    @abstractmethod
    def delete_object(self, key: str) -> None:
        """Guarded. Only used by ``serena cloud-sync test`` to clean up its probe."""

    # ---- convenience ------------------------------------------------------
    def close(self) -> None:
        """Release any provider-held resources (connection pools, etc)."""
        return None
