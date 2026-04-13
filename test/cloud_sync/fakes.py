"""In-memory CloudStorageProvider used for every unit test in this package."""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Iterator

from serena.cloud_sync.exceptions import ProviderConflictError
from serena.cloud_sync.provider import META_SHA256, META_SIZE, CloudStorageProvider, RemoteObjectMeta


class FakeCloudProvider(CloudStorageProvider):
    """Thread-safe in-memory store that mimics S3-ish semantics."""

    supports_multipart = False
    supports_conditional_put = True
    supports_object_metadata = True
    supports_server_side_copy = False

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: dict[str, tuple[bytes, dict[str, str], datetime]] = {}
        self.last_content_type: dict[str, str] = {}

    # ---- primitives -------------------------------------------------------

    def list_objects(self, prefix: str) -> Iterator[RemoteObjectMeta]:
        with self._lock:
            items = [(k, v) for k, v in self._store.items() if k.startswith(prefix)]
        for k, (body, meta, ts) in items:
            sha = meta.get(META_SHA256)
            yield RemoteObjectMeta(
                key=k,
                size=len(body),
                sha256=sha,
                etag=f"\"{sha[:16]}\"" if sha else None,
                last_modified=ts,
                metadata_present=sha is not None,
                raw_metadata=dict(meta),
            )

    def head_object(self, key: str) -> RemoteObjectMeta | None:
        with self._lock:
            entry = self._store.get(key)
        if entry is None:
            return None
        body, meta, ts = entry
        sha = meta.get(META_SHA256)
        return RemoteObjectMeta(
            key=key,
            size=len(body),
            sha256=sha,
            etag=f"\"{sha[:16]}\"" if sha else None,
            last_modified=ts,
            metadata_present=sha is not None,
            raw_metadata=dict(meta),
        )

    def get_object(self, key: str) -> bytes:
        with self._lock:
            entry = self._store.get(key)
        if entry is None:
            raise KeyError(key)
        return entry[0]

    def iter_object(self, key: str, chunk_size: int = 1024 * 1024):
        body = self.get_object(key)
        for i in range(0, len(body), chunk_size):
            yield body[i: i + chunk_size]

    def put_object(self, key: str, data: bytes, sha256_hex: str,
                   content_type: str = "application/octet-stream") -> None:
        with self._lock:
            self._store[key] = (bytes(data), {META_SHA256: sha256_hex, META_SIZE: str(len(data))},
                                datetime.now(timezone.utc))
            self.last_content_type[key] = content_type

    def put_object_if_absent(self, key: str, data: bytes, sha256_hex: str,
                             content_type: str = "application/octet-stream") -> bool:
        with self._lock:
            if key in self._store:
                existing = self._store[key][1].get(META_SHA256)
                if existing == sha256_hex:
                    return False
                raise ProviderConflictError(f"{key} already exists with different content",
                                            provider_code="412")
            self._store[key] = (bytes(data), {META_SHA256: sha256_hex, META_SIZE: str(len(data))},
                                datetime.now(timezone.utc))
            self.last_content_type[key] = content_type
        return True

    def delete_object(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    # ---- test-only helpers ------------------------------------------------

    def seed(self, key: str, body: bytes, sha: str | None = None) -> None:
        if sha is None:
            import hashlib
            sha = hashlib.sha256(body).hexdigest()
        self.put_object(key, body, sha)

    def raw(self, key: str) -> bytes:
        return self._store[key][0]

    def keys(self) -> list[str]:
        return sorted(self._store.keys())
