import hashlib
from pathlib import Path

from serena.cloud_sync.diff import SyncAction, classify
from serena.cloud_sync.inventory import LocalInventory, LocalObjectMeta, RemoteInventory
from serena.cloud_sync.provider import RemoteObjectMeta


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _local(key: str, path: Path, body: bytes) -> LocalObjectMeta:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return LocalObjectMeta(
        remote_key=key, abs_path=path, size=len(body), sha256=_sha(body), scope_origin="global",
    )


def _remote(key: str, body: bytes) -> RemoteObjectMeta:
    sha = _sha(body)
    return RemoteObjectMeta(key=key, size=len(body), sha256=sha, metadata_present=True)


def test_upload_download_skip(tmp_path: Path) -> None:
    local = LocalInventory()
    remote = RemoteInventory()

    local.entries["a"] = _local("a", tmp_path / "a", b"only-local")
    remote.entries["b"] = _remote("b", b"only-remote")
    local.entries["c"] = _local("c", tmp_path / "c", b"same")
    remote.entries["c"] = _remote("c", b"same")

    plan = classify(local, remote)
    actions = {e.key: e.action for e in plan.entries}
    assert actions["a"] is SyncAction.UPLOAD
    assert actions["b"] is SyncAction.DOWNLOAD
    assert actions["c"] is SyncAction.SKIP
    assert plan.counts()["upload"] == 1
    assert plan.counts()["download"] == 1
    assert plan.counts()["skip"] == 1


def test_conflict(tmp_path: Path) -> None:
    local = LocalInventory()
    remote = RemoteInventory()
    local.entries["k"] = _local("k", tmp_path / "k", b"LOCAL")
    remote.entries["k"] = _remote("k", b"REMOTE-DIFFERENT")

    plan = classify(local, remote)
    e = plan.entries[0]
    assert e.action is SyncAction.CONFLICT
    assert "sha256 mismatch" in e.reason


def test_remote_without_metadata_is_conflict(tmp_path: Path) -> None:
    """Defensive: if an older / alien object lacks our sha256 metadata and the
    hash_fallback pass didn't run, classify must not silently choose a side."""
    local = LocalInventory()
    remote = RemoteInventory()
    local.entries["k"] = _local("k", tmp_path / "k", b"LOCAL")
    remote.entries["k"] = RemoteObjectMeta(key="k", size=5, sha256=None, metadata_present=False)
    plan = classify(local, remote)
    assert plan.entries[0].action is SyncAction.CONFLICT
    assert "missing sha256" in plan.entries[0].reason
