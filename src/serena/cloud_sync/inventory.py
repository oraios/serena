"""Local + remote inventory builders.

Inventory entries are provider-neutral; the provider adapter translates its
SDK response into ``RemoteObjectMeta`` records already.
"""
from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from serena.cloud_sync.hash_util import sha256_file, sha256_stream
from serena.cloud_sync.provider import CloudStorageProvider, RemoteObjectMeta
from serena.cloud_sync.scope import ScopeFilter, ScopeRoot

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class LocalObjectMeta:
    """Local-side inventory entry for a single file."""
    remote_key: str
    abs_path: Path
    size: int
    sha256: str
    scope_origin: str  # "global" or "project:<slug>"


@dataclass
class LocalInventory:
    """Map from remote-key -> LocalObjectMeta."""
    entries: dict[str, LocalObjectMeta] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self):
        return iter(self.entries.values())

    def get(self, key: str) -> LocalObjectMeta | None:
        return self.entries.get(key)


@dataclass
class RemoteInventory:
    """Map from remote-key -> RemoteObjectMeta."""
    entries: dict[str, RemoteObjectMeta] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self):
        return iter(self.entries.values())

    def get(self, key: str) -> RemoteObjectMeta | None:
        return self.entries.get(key)


def build_local_inventory(
    scope: ScopeFilter,
    roots: Iterable[ScopeRoot],
    root_prefix: str,
) -> LocalInventory:
    """Walk all ``roots``, honoring ``scope``, and hash every included file."""
    inv = LocalInventory()
    for root, abs_path, rel in scope.iter_files(list(roots)):
        rel_norm = _norm_rel(rel)
        key = _compose_key(root_prefix, root.remote_subprefix, rel_norm)
        size = abs_path.stat().st_size
        digest = sha256_file(abs_path)
        inv.entries[key] = LocalObjectMeta(
            remote_key=key,
            abs_path=abs_path,
            size=size,
            sha256=digest,
            scope_origin=root.remote_subprefix.strip("/") or "global",
        )
    return inv


def build_remote_inventory(
    provider: CloudStorageProvider,
    prefix: str,
    *,
    hash_fallback: bool = False,
) -> RemoteInventory:
    """List ``prefix`` on ``provider`` and build the remote inventory.

    If ``hash_fallback=True``, any object missing our sha256 metadata will be
    stream-hashed (once per run; caching is in a future enhancement).
    """
    inv = RemoteInventory()
    for meta in provider.list_objects(prefix):
        # ListObjects rarely returns metadata; HEAD to fetch it.
        if not meta.metadata_present:
            full = provider.head_object(meta.key)
            if full is not None:
                meta = full
        if meta.sha256 is None and hash_fallback:
            digest = sha256_stream(provider.iter_object(meta.key))
            meta = RemoteObjectMeta(
                key=meta.key,
                size=meta.size,
                sha256=digest,
                etag=meta.etag,
                version_id=meta.version_id,
                last_modified=meta.last_modified,
                metadata_present=False,
                raw_metadata=meta.raw_metadata,
            )
        inv.entries[meta.key] = meta
    return inv


def _norm_rel(rel_posix: str) -> str:
    """POSIX-style, Unicode NFC normalized relpath for a stable remote key."""
    return unicodedata.normalize("NFC", rel_posix.replace("\\", "/").lstrip("/"))


def _compose_key(root_prefix: str, subprefix: str, rel_norm: str) -> str:
    rp = root_prefix.rstrip("/") + "/"
    sub = subprefix.strip("/")
    if sub:
        return f"{rp}{sub}/{rel_norm}"
    return f"{rp}{rel_norm}"
