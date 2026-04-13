"""CloudSyncService — the orchestrator.

Receives the provider via constructor injection (DIP). Contains only business
logic; never imports ``boto3`` or ``azure.storage.blob``.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from serena.cloud_sync.diff import DiffEntry, DiffPlan, SyncAction, classify
from serena.cloud_sync.exceptions import ProviderConflictError
from serena.cloud_sync.hash_util import byte_compare_file_to_stream
from serena.cloud_sync.inventory import (
    LocalInventory,
    RemoteInventory,
    build_local_inventory,
    build_remote_inventory,
)
from serena.cloud_sync.provider import CloudStorageProvider
from serena.cloud_sync.scope import ScopeFilter, ScopeRoot, enforce_no_credential_files

log = logging.getLogger(__name__)


@dataclass
class SyncPlan:
    """Dry-run result. Used by both CLI and dashboard as the "confirm" surface."""
    counts: dict[str, int]
    entries: list[dict]

    @classmethod
    def from_diff(cls, diff: DiffPlan) -> "SyncPlan":
        return cls(
            counts=diff.counts(),
            entries=[
                {
                    "key": e.key,
                    "action": e.action.value,
                    "local_size": e.local.size if e.local else None,
                    "remote_size": e.remote.size if e.remote else None,
                    "reason": e.reason,
                }
                for e in diff.entries
            ],
        )


@dataclass
class SyncReport:
    """Post-execution outcome."""
    mode: str  # "push" | "pull"
    started_at: str
    finished_at: str | None = None
    uploaded: list[str] = field(default_factory=list)
    downloaded: list[str] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    dry_run: bool = False
    plan: SyncPlan | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.plan is not None:
            d["plan"] = {"counts": self.plan.counts, "entries": self.plan.entries}
        return d


class CloudSyncService:
    """Push / pull orchestrator. The provider is injected via the constructor."""

    def __init__(
        self,
        provider: CloudStorageProvider,
        scope: ScopeFilter,
        roots: Iterable[ScopeRoot],
        root_prefix: str,
        progress_path: Path | None = None,
    ) -> None:
        self._provider = provider
        self._scope = scope
        self._roots = list(roots)
        self._root_prefix = root_prefix.rstrip("/") + "/"
        self._progress_path = progress_path

    # ---- plan building ----------------------------------------------------

    def build_plan(self, *, hash_fallback: bool = True) -> tuple[LocalInventory, RemoteInventory, DiffPlan]:
        local = build_local_inventory(self._scope, self._roots, self._root_prefix)
        remote = build_remote_inventory(
            self._provider, self._root_prefix, hash_fallback=hash_fallback,
        )
        diff = classify(local, remote)
        return local, remote, diff

    # ---- push -------------------------------------------------------------

    def push(self, *, dry_run: bool = False, force: bool = False,
             byte_compare: bool = False) -> SyncReport:
        local, remote, diff = self.build_plan()
        report = SyncReport(
            mode="push",
            started_at=_iso_utc(),
            dry_run=dry_run,
            plan=SyncPlan.from_diff(diff),
        )
        if dry_run:
            report.finished_at = _iso_utc()
            return report

        for entry in diff.entries:
            try:
                if entry.action is SyncAction.UPLOAD:
                    self._do_upload(entry, report)
                elif entry.action is SyncAction.SKIP:
                    if byte_compare:
                        self._do_byte_compare(entry, report)
                    else:
                        report.skipped.append(entry.key)
                elif entry.action is SyncAction.CONFLICT:
                    if force:
                        self._do_force_upload(entry, report)
                    else:
                        report.conflicts.append(self._conflict_record(entry, resolution="kept-remote"))
                # DOWNLOAD entries are no-ops on push.
            except Exception as exc:  # pragma: no cover - logged + recorded
                log.error("push failed for %s: %s", entry.key, exc, exc_info=exc)
                report.failed.append({"key": entry.key, "error": str(exc)})
            self._write_progress(report)

        report.finished_at = _iso_utc()
        self._write_progress(report)
        return report

    def _do_upload(self, entry: DiffEntry, report: SyncReport) -> None:
        assert entry.local is not None
        enforce_no_credential_files(entry.local.abs_path.name)
        with open(entry.local.abs_path, "rb") as fh:
            data = fh.read()
        try:
            written = self._provider.put_object_if_absent(
                entry.key, data, entry.local.sha256
            )
            if written:
                report.uploaded.append(entry.key)
            else:
                report.skipped.append(entry.key)
        except ProviderConflictError:
            report.conflicts.append(self._conflict_record(entry, resolution="kept-remote"))

    def _do_force_upload(self, entry: DiffEntry, report: SyncReport) -> None:
        assert entry.local is not None
        enforce_no_credential_files(entry.local.abs_path.name)
        with open(entry.local.abs_path, "rb") as fh:
            data = fh.read()
        self._provider.put_object(entry.key, data, entry.local.sha256)
        report.uploaded.append(entry.key)

    # ---- pull -------------------------------------------------------------

    def pull(self, *, dry_run: bool = False, force: bool = False,
             byte_compare: bool = False) -> SyncReport:
        local, remote, diff = self.build_plan()
        report = SyncReport(
            mode="pull",
            started_at=_iso_utc(),
            dry_run=dry_run,
            plan=SyncPlan.from_diff(diff),
        )
        if dry_run:
            report.finished_at = _iso_utc()
            return report

        for entry in diff.entries:
            try:
                if entry.action is SyncAction.DOWNLOAD:
                    self._do_download(entry, report)
                elif entry.action is SyncAction.SKIP:
                    if byte_compare:
                        self._do_byte_compare(entry, report)
                    else:
                        report.skipped.append(entry.key)
                elif entry.action is SyncAction.CONFLICT:
                    if force:
                        self._do_force_download(entry, report, overwrite=True)
                    else:
                        self._do_conflict_sibling(entry, report)
                # UPLOAD entries are no-ops on pull.
            except Exception as exc:  # pragma: no cover
                log.error("pull failed for %s: %s", entry.key, exc, exc_info=exc)
                report.failed.append({"key": entry.key, "error": str(exc)})
            self._write_progress(report)

        report.finished_at = _iso_utc()
        self._write_progress(report)
        return report

    def _do_download(self, entry: DiffEntry, report: SyncReport) -> None:
        assert entry.remote is not None
        # Resolve target path: find matching scope root, strip the key prefix
        target = self._key_to_local_path(entry.key)
        if target is None:
            report.failed.append({"key": entry.key, "error": "no matching scope root"})
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        data = self._provider.get_object(entry.key)
        _atomic_write(target, data)
        report.downloaded.append(entry.key)

    def _do_force_download(self, entry: DiffEntry, report: SyncReport, *, overwrite: bool) -> None:
        assert entry.remote is not None
        target = self._key_to_local_path(entry.key)
        if target is None:
            report.failed.append({"key": entry.key, "error": "no matching scope root"})
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        data = self._provider.get_object(entry.key)
        _atomic_write(target, data)
        report.downloaded.append(entry.key)

    def _do_conflict_sibling(self, entry: DiffEntry, report: SyncReport) -> None:
        assert entry.remote is not None
        target = self._key_to_local_path(entry.key)
        if target is None:
            report.failed.append({"key": entry.key, "error": "no matching scope root"})
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        data = self._provider.get_object(entry.key)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        sibling = target.with_name(target.name + f".cloud-{ts}")
        _atomic_write(sibling, data)
        report.conflicts.append(self._conflict_record(entry, resolution=f"remote-saved-as:{sibling.name}"))

    def _do_byte_compare(self, entry: DiffEntry, report: SyncReport) -> None:
        if entry.local is None or entry.remote is None:
            report.skipped.append(entry.key)
            return
        chunks = self._provider.iter_object(entry.key)
        if byte_compare_file_to_stream(entry.local.abs_path, chunks):
            report.skipped.append(entry.key)
        else:
            # Diverged despite sha256 match: record as conflict without action.
            report.conflicts.append(self._conflict_record(entry, resolution="byte-compare-mismatch"))

    # ---- helpers ----------------------------------------------------------

    def _key_to_local_path(self, key: str) -> Path | None:
        """Reverse the _compose_key mapping to find the correct local path."""
        for root in self._roots:
            rp = self._root_prefix
            sub = root.remote_subprefix.strip("/")
            prefix = rp + (sub + "/" if sub else "")
            if key.startswith(prefix):
                rel = key[len(prefix):]
                return root.local_root / rel
        return None

    def _conflict_record(self, entry: DiffEntry, *, resolution: str) -> dict:
        return {
            "key": entry.key,
            "resolution": resolution,
            "local_sha256": entry.local.sha256 if entry.local else None,
            "remote_sha256": entry.remote.sha256 if entry.remote else None,
            "reason": entry.reason,
        }

    def _write_progress(self, report: SyncReport) -> None:
        if self._progress_path is None:
            return
        try:
            self._progress_path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(self._progress_path, json.dumps(report.to_dict(), indent=2).encode("utf-8"))
        except Exception as exc:
            log.debug("progress write failed: %s", exc)


def _iso_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write(path: Path, data: bytes) -> None:
    """Atomic write: tmp + fsync + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmpname = tempfile.mkstemp(
        prefix=path.name + ".cloud-sync.tmp.",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmpname, path)
    except Exception:
        try:
            os.unlink(tmpname)
        except OSError:
            pass
        raise
