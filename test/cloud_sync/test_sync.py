from pathlib import Path

import pytest

from serena.cloud_sync.diff import SyncAction
from serena.cloud_sync.scope import ScopeFilter, ScopeRoot
from serena.cloud_sync.sync import CloudSyncService

from .fakes import FakeCloudProvider


ROOT_PREFIX = "serena-sync/"


def _make_service(tmp_path: Path, provider: FakeCloudProvider,
                  opt_in_local_yml: bool = False) -> tuple[CloudSyncService, ScopeRoot]:
    root = ScopeRoot(local_root=tmp_path, remote_subprefix="global")
    scope = ScopeFilter(
        include_patterns=("memories/**/*.md", "serena_config.yml"),
        opt_in_project_local_yml=opt_in_local_yml,
    )
    return CloudSyncService(
        provider=provider,
        scope=scope,
        roots=[root],
        root_prefix=ROOT_PREFIX,
    ), root


def _write(path: Path, body: str = "hi") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


def test_push_uploads_local_only(tmp_path: Path) -> None:
    provider = FakeCloudProvider()
    _write(tmp_path / "serena_config.yml", "a: 1")
    _write(tmp_path / "memories" / "one.md", "m1")
    _write(tmp_path / "memories" / "two.md", "m2")

    service, _ = _make_service(tmp_path, provider)
    report = service.push(dry_run=False)
    assert sorted(report.uploaded) == [
        "serena-sync/global/memories/one.md",
        "serena-sync/global/memories/two.md",
        "serena-sync/global/serena_config.yml",
    ]
    assert not report.conflicts
    assert not report.failed


def test_pull_downloads_remote_only(tmp_path: Path) -> None:
    provider = FakeCloudProvider()
    provider.seed("serena-sync/global/memories/x.md", b"remote body")

    service, _ = _make_service(tmp_path, provider)
    report = service.pull(dry_run=False)
    assert "serena-sync/global/memories/x.md" in report.downloaded
    assert (tmp_path / "memories" / "x.md").read_bytes() == b"remote body"


def test_conflict_push_preserves_remote(tmp_path: Path) -> None:
    provider = FakeCloudProvider()
    key = "serena-sync/global/memories/x.md"
    provider.seed(key, b"REMOTE")
    _write(tmp_path / "memories" / "x.md", "LOCAL")

    service, _ = _make_service(tmp_path, provider)
    report = service.push(dry_run=False)
    # remote unchanged
    assert provider.raw(key) == b"REMOTE"
    assert len(report.conflicts) == 1
    assert report.conflicts[0]["resolution"] == "kept-remote"


def test_conflict_pull_saves_sibling(tmp_path: Path) -> None:
    provider = FakeCloudProvider()
    key = "serena-sync/global/memories/x.md"
    provider.seed(key, b"REMOTE")
    target = tmp_path / "memories" / "x.md"
    _write(target, "LOCAL")

    service, _ = _make_service(tmp_path, provider)
    report = service.pull(dry_run=False)
    # local untouched
    assert target.read_text() == "LOCAL"
    # sibling created with .cloud-<ts> suffix containing remote body
    siblings = list((tmp_path / "memories").glob("x.md.cloud-*"))
    assert len(siblings) == 1
    assert siblings[0].read_bytes() == b"REMOTE"
    assert report.conflicts[0]["resolution"].startswith("remote-saved-as:")


def test_force_push_overwrites_conflict(tmp_path: Path) -> None:
    provider = FakeCloudProvider()
    key = "serena-sync/global/memories/x.md"
    provider.seed(key, b"REMOTE")
    _write(tmp_path / "memories" / "x.md", "LOCAL-NEW")

    service, _ = _make_service(tmp_path, provider)
    report = service.push(dry_run=False, force=True)
    assert provider.raw(key) == b"LOCAL-NEW"
    assert key in report.uploaded


def test_dry_run_no_mutation(tmp_path: Path) -> None:
    provider = FakeCloudProvider()
    _write(tmp_path / "memories" / "x.md", "LOCAL")
    service, _ = _make_service(tmp_path, provider)
    report = service.push(dry_run=True)
    assert report.dry_run
    assert report.plan is not None
    assert not report.uploaded
    assert not provider.keys()  # remote still empty


def test_idempotent_push(tmp_path: Path) -> None:
    provider = FakeCloudProvider()
    _write(tmp_path / "memories" / "x.md", "HELLO")
    service, _ = _make_service(tmp_path, provider)
    r1 = service.push(dry_run=False)
    r2 = service.push(dry_run=False)
    assert len(r1.uploaded) == 1
    assert len(r2.uploaded) == 0
    assert len(r2.skipped) == 1


def test_no_boto3_in_business_logic() -> None:
    """Guard: business logic modules must not import boto3 / azure SDKs."""
    import importlib
    mods = [
        "serena.cloud_sync.sync",
        "serena.cloud_sync.diff",
        "serena.cloud_sync.inventory",
        "serena.cloud_sync.scope",
        "serena.cloud_sync.hash_util",
        "serena.cloud_sync.credentials",
        "serena.cloud_sync.provider",
    ]
    for name in mods:
        m = importlib.import_module(name)
        src = getattr(m, "__dict__")
        banned = {"boto3", "botocore", "azure"}
        for k in banned:
            assert k not in src, f"{name} must not import {k}"
