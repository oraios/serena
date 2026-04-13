"""CLI subcommand group for ``serena cloud-sync``.

This module keeps CLI logic out of ``serena.cli`` and out of ``sync.py``.
``serena.cli`` registers the group via a tiny one-liner at its bottom.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import sys
import time
from pathlib import Path
from typing import Iterable

import click

from serena.cloud_sync.credentials import (
    ENV_PATH,
    K_AZ_ACCOUNT,
    K_AZ_CONTAINER,
    K_AZ_ENDPOINT_SUFFIX,
    K_AZ_KEY,
    K_PROVIDER,
    K_R2_ACCESS_KEY_ID,
    K_R2_ACCOUNT_ID,
    K_R2_BUCKET,
    K_R2_ENDPOINT_URL,
    K_R2_SECRET_ACCESS_KEY,
    K_ROOT_PREFIX,
    K_S3_ACCESS_KEY_ID,
    K_S3_BUCKET,
    K_S3_ENDPOINT_URL,
    K_S3_REGION,
    K_S3_SECRET_ACCESS_KEY,
    check_not_in_git,
    check_perms,
    ensure_home,
    fix_perms,
    install_redactor,
    load_settings,
    save_env,
)
from serena.cloud_sync.exceptions import CloudSyncError, CredentialError
from serena.cloud_sync.factory import build_provider
from serena.cloud_sync.scope import DEFAULT_GLOBAL_INCLUDES, DEFAULT_PROJECT_INCLUDES, ScopeFilter, ScopeRoot
from serena.cloud_sync.settings import CloudSyncSettings, DEFAULT_ROOT_PREFIX, ProviderType
from serena.cloud_sync.sync import CloudSyncService, SyncReport
from serena.util.cli_util import AutoRegisteringGroup

log = logging.getLogger(__name__)

_MAX_CONTENT_WIDTH = 120


def _discover_project_roots(cwd: Path | None = None) -> list[ScopeRoot]:
    """Discover the set of local roots to sync.

    Currently:
    - Global: $SERENA_HOME (default ~/.serena)
    - Project: any ancestor of cwd that contains a .serena dir.
    """
    from serena.config.serena_config import SerenaPaths
    home = Path(SerenaPaths().serena_user_home_dir)
    roots: list[ScopeRoot] = [
        ScopeRoot(local_root=home, remote_subprefix="global"),
    ]
    cwd = cwd or Path.cwd()
    for parent in [cwd, *cwd.parents]:
        dotser = parent / ".serena"
        if dotser.is_dir():
            slug = _project_slug(parent)
            roots.append(ScopeRoot(local_root=dotser, remote_subprefix=f"projects/{slug}"))
            break
    return roots


def _project_slug(abs_path: Path) -> str:
    """Deterministic, collision-resistant, privacy-preserving project slug."""
    import hashlib
    h = hashlib.sha256(str(abs_path.resolve()).encode("utf-8")).hexdigest()[:12]
    basename = abs_path.name or "root"
    return f"{h}-{basename}"


def _build_scope(opt_in_local_yml: bool) -> ScopeFilter:
    includes = list(DEFAULT_GLOBAL_INCLUDES) + list(DEFAULT_PROJECT_INCLUDES)
    return ScopeFilter(
        include_patterns=tuple(includes),
        opt_in_project_local_yml=opt_in_local_yml,
    )


def _build_service(
    settings: CloudSyncSettings,
    *,
    opt_in_local_yml: bool,
) -> tuple[CloudSyncService, list[ScopeRoot]]:
    provider = build_provider(settings)
    scope = _build_scope(opt_in_local_yml)
    roots = _discover_project_roots()
    progress_path = Path(os.path.expanduser("~/.serena")) / "cloud-sync.progress.json"
    return (
        CloudSyncService(
            provider=provider,
            scope=scope,
            roots=roots,
            root_prefix=settings.root_prefix,
            progress_path=progress_path,
        ),
        roots,
    )


def _load_or_exit() -> CloudSyncSettings:
    try:
        settings = load_settings()
    except CredentialError as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(2)
    install_redactor(log, settings)
    install_redactor(logging.getLogger("serena.cloud_sync"), settings)
    return settings


def _print_report(report: SyncReport, *, fmt: str) -> None:
    if fmt == "json":
        click.echo(json.dumps(report.to_dict(), indent=2))
        return
    if report.plan is not None:
        click.echo(f"plan: {report.plan.counts}")
    click.echo(
        f"{report.mode} {'(dry-run) ' if report.dry_run else ''}"
        f"uploaded={len(report.uploaded)} "
        f"downloaded={len(report.downloaded)} "
        f"conflicts={len(report.conflicts)} "
        f"skipped={len(report.skipped)} "
        f"failed={len(report.failed)}"
    )
    for c in report.conflicts:
        click.echo(f"  conflict: {c['key']} -> {c['resolution']}", err=True)
    for f in report.failed:
        click.echo(f"  failed: {f['key']} -> {f['error']}", err=True)


class CloudSyncCommands(AutoRegisteringGroup):
    """Group for ``serena cloud-sync`` subcommands (EXPERIMENTAL)."""

    def __init__(self) -> None:
        super().__init__(
            name="cloud-sync",
            help=(
                "EXPERIMENTAL. Sync serena memories + config to a cloud backend "
                "(Cloudflare R2, Amazon S3, Azure Blob). Additive only — never "
                "silently overwrites divergent content."
            ),
        )

    # ---- configure --------------------------------------------------------

    @staticmethod
    @click.command("configure", help="Interactive credential configuration.",
                   context_settings={"max_content_width": _MAX_CONTENT_WIDTH})
    @click.option("--provider", type=click.Choice([p.value for p in ProviderType]),
                  default=None, help="Active provider.")
    @click.option("--from-stdin", is_flag=True, help="Read JSON {key:value} from stdin (scriptable).")
    def configure(provider: str | None, from_stdin: bool) -> None:
        ensure_home()
        if from_stdin:
            raw = json.loads(sys.stdin.read() or "{}")
            save_env(raw)
            fix_perms()
            check_not_in_git()
            click.echo(f"wrote {ENV_PATH}")
            return

        values: dict[str, str] = {}
        if provider:
            values[K_PROVIDER] = provider
        else:
            current = _current_provider_value()
            values[K_PROVIDER] = click.prompt(
                "Provider (r2/s3/azure)", default=current or "r2",
                type=click.Choice([p.value for p in ProviderType]),
            )
        values[K_ROOT_PREFIX] = click.prompt(
            "Root prefix", default=DEFAULT_ROOT_PREFIX
        )
        p = values[K_PROVIDER]
        if p == "r2":
            values[K_R2_ACCOUNT_ID] = click.prompt("R2 account ID")
            values[K_R2_ACCESS_KEY_ID] = click.prompt("R2 access key ID")
            values[K_R2_SECRET_ACCESS_KEY] = click.prompt(
                "R2 secret access key", hide_input=True
            )
            values[K_R2_BUCKET] = click.prompt("R2 bucket")
            values[K_R2_ENDPOINT_URL] = click.prompt(
                "R2 endpoint URL (leave blank to derive from account id)", default="",
            )
        elif p == "s3":
            values[K_S3_ACCESS_KEY_ID] = click.prompt("AWS access key ID")
            values[K_S3_SECRET_ACCESS_KEY] = click.prompt(
                "AWS secret access key", hide_input=True
            )
            values[K_S3_BUCKET] = click.prompt("AWS bucket")
            values[K_S3_REGION] = click.prompt("AWS region", default="us-east-1")
            values[K_S3_ENDPOINT_URL] = click.prompt(
                "Custom endpoint URL (MinIO/Ceph; leave blank for AWS)", default="",
            )
        elif p == "azure":
            values[K_AZ_ACCOUNT] = click.prompt("Azure storage account name")
            values[K_AZ_KEY] = click.prompt(
                "Azure storage account key", hide_input=True
            )
            values[K_AZ_CONTAINER] = click.prompt("Azure container")
            values[K_AZ_ENDPOINT_SUFFIX] = click.prompt(
                "Azure endpoint suffix", default="core.windows.net"
            )
        save_env(values)
        fix_perms()
        check_not_in_git()
        click.echo(f"wrote {ENV_PATH} (chmod 600)")

    # ---- test -------------------------------------------------------------

    @staticmethod
    @click.command("test", help="Round-trip a probe object to validate credentials.")
    @click.option("--json", "as_json", is_flag=True, help="Emit JSON result.")
    def test(as_json: bool) -> None:
        settings = _load_or_exit()
        provider = build_provider(settings)
        probe_key = f"{settings.root_prefix.rstrip('/')}/.self-test/{int(time.time())}-{socket.gethostname()}"
        body = f"serena cloud-sync self-test {time.time()}".encode("utf-8")
        from serena.cloud_sync.hash_util import sha256_bytes
        sha = sha256_bytes(body)
        result = {"probe_key": probe_key, "ok": False}
        try:
            provider.put_object_if_absent(probe_key, body, sha)
            got = provider.get_object(probe_key)
            result["round_trip_ok"] = got == body
            provider.delete_object(probe_key)
            result["ok"] = True
        except CloudSyncError as e:
            result["error"] = str(e)
        finally:
            provider.close()
        if as_json:
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo(f"probe: {probe_key}  ok={result['ok']}")
        sys.exit(0 if result["ok"] else 1)

    # ---- status -----------------------------------------------------------

    @staticmethod
    @click.command("status", help="Show inventory counts and last sync markers.")
    @click.option("--include-project-local-yml", is_flag=True)
    def status(include_project_local_yml: bool) -> None:
        settings = _load_or_exit()
        service, roots = _build_service(settings, opt_in_local_yml=include_project_local_yml)
        local, remote, diff = service.build_plan()
        out = {
            "provider": settings.provider.value,
            "root_prefix": settings.root_prefix,
            "roots": [{"path": str(r.local_root), "remote_subprefix": r.remote_subprefix} for r in roots],
            "local_count": len(local),
            "remote_count": len(remote),
            "plan_counts": diff.counts(),
        }
        click.echo(json.dumps(out, indent=2))

    # ---- push -------------------------------------------------------------

    @staticmethod
    @click.command("push", help="Upload local files that are absent or classified as upload.")
    @click.option("--dry-run", is_flag=True)
    @click.option("--force-push", "force", is_flag=True,
                  help="Overwrite remote on CONFLICT. Use with care.")
    @click.option("--byte-compare", is_flag=True, help="Paranoid byte-by-byte compare after sha256 match.")
    @click.option("--include-project-local-yml", is_flag=True)
    @click.option("--json", "as_json", is_flag=True)
    def push(dry_run: bool, force: bool, byte_compare: bool,
             include_project_local_yml: bool, as_json: bool) -> None:
        settings = _load_or_exit()
        service, _ = _build_service(settings, opt_in_local_yml=include_project_local_yml)
        report = service.push(dry_run=dry_run, force=force, byte_compare=byte_compare)
        _print_report(report, fmt="json" if as_json else "text")
        sys.exit(1 if report.failed else 0)

    # ---- pull -------------------------------------------------------------

    @staticmethod
    @click.command("pull", help="Download remote files that are absent locally.")
    @click.option("--dry-run", is_flag=True)
    @click.option("--force-pull", "force", is_flag=True,
                  help="Overwrite local on CONFLICT. Use with care.")
    @click.option("--byte-compare", is_flag=True)
    @click.option("--include-project-local-yml", is_flag=True)
    @click.option("--json", "as_json", is_flag=True)
    def pull(dry_run: bool, force: bool, byte_compare: bool,
             include_project_local_yml: bool, as_json: bool) -> None:
        settings = _load_or_exit()
        service, _ = _build_service(settings, opt_in_local_yml=include_project_local_yml)
        report = service.pull(dry_run=dry_run, force=force, byte_compare=byte_compare)
        _print_report(report, fmt="json" if as_json else "text")
        sys.exit(1 if report.failed else 0)

    # ---- fix-perms --------------------------------------------------------

    @staticmethod
    @click.command("fix-perms", help="Fix credentials file permissions (chmod 0600).")
    def fix_perms_cmd() -> None:
        fix_perms()
        check_perms()
        click.echo(f"{ENV_PATH} is 0600")


def _current_provider_value() -> str | None:
    try:
        return load_settings().provider.value
    except Exception:
        return None


cloud_sync_group = CloudSyncCommands()
