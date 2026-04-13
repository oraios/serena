"""Diff / reconciliation classifier.

Pure, SDK-free. Given a LocalInventory and a RemoteInventory, classify every
key into one of the ``SyncAction`` values.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from serena.cloud_sync.inventory import LocalInventory, LocalObjectMeta, RemoteInventory
from serena.cloud_sync.provider import RemoteObjectMeta


class SyncAction(str, Enum):
    UPLOAD = "upload"
    DOWNLOAD = "download"
    SKIP = "skip"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class DiffEntry:
    key: str
    action: SyncAction
    local: LocalObjectMeta | None = None
    remote: RemoteObjectMeta | None = None
    reason: str = ""


@dataclass
class DiffPlan:
    entries: list[DiffEntry] = field(default_factory=list)

    def by_action(self, action: SyncAction) -> list[DiffEntry]:
        return [e for e in self.entries if e.action is action]

    def counts(self) -> dict[str, int]:
        c = {a.value: 0 for a in SyncAction}
        for e in self.entries:
            c[e.action.value] += 1
        return c


def classify(
    local: LocalInventory,
    remote: RemoteInventory,
) -> DiffPlan:
    keys = set(local.entries.keys()) | set(remote.entries.keys())
    plan = DiffPlan()
    for k in sorted(keys):
        lm = local.get(k)
        rm = remote.get(k)
        if lm is not None and rm is None:
            plan.entries.append(DiffEntry(k, SyncAction.UPLOAD, lm, None, "local-only"))
            continue
        if rm is not None and lm is None:
            plan.entries.append(DiffEntry(k, SyncAction.DOWNLOAD, None, rm, "remote-only"))
            continue
        assert lm is not None and rm is not None  # key set guarantees
        if rm.sha256 is None:
            # Remote sha256 missing despite hash_fallback=True — treat as
            # unknown. Classify as CONFLICT so the user sees it; safer than
            # silent overwrite in either direction.
            plan.entries.append(DiffEntry(k, SyncAction.CONFLICT, lm, rm,
                                          "remote missing sha256 metadata"))
            continue
        if lm.sha256 == rm.sha256 and lm.size == rm.size:
            plan.entries.append(DiffEntry(k, SyncAction.SKIP, lm, rm, "identical"))
            continue
        plan.entries.append(DiffEntry(k, SyncAction.CONFLICT, lm, rm,
                                      f"sha256 mismatch (local={lm.sha256[:8]} remote={rm.sha256[:8]})"))
    return plan
