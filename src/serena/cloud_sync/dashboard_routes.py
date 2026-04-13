"""Flask blueprint for the cloud-sync dashboard panel.

Registered from ``serena.dashboard`` at app-construction time. All routes
return JSON; secret values are masked on GET and treated as 'unchanged' on
POST when the sentinel ``****`` is submitted.
"""
from __future__ import annotations

import logging
import secrets
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request, abort

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
    env_exists,
    fix_perms,
    install_redactor,
    load_settings,
    save_env,
)
from serena.cloud_sync.exceptions import CloudSyncError, CredentialError
from serena.cloud_sync.factory import build_provider
from serena.cloud_sync.hash_util import sha256_bytes
from serena.cloud_sync.scope import DEFAULT_GLOBAL_INCLUDES, DEFAULT_PROJECT_INCLUDES, ScopeFilter
from serena.cloud_sync.settings import CloudSyncSettings, DEFAULT_ROOT_PREFIX, ProviderType
from serena.cloud_sync.sync import CloudSyncService, SyncReport

log = logging.getLogger(__name__)

bp = Blueprint("cloud_sync", __name__, url_prefix="/api/cloud-sync")

# Local-process defense against CSRF from other processes on localhost.
# The token is generated once per process and returned only to requests from
# 127.0.0.1/::1 on the bootstrap endpoint. Every other endpoint requires the
# token in X-Cloud-Sync-Token. This is defense-in-depth — the dashboard is
# already bound to 127.0.0.1 — but prevents same-origin-ish mischief from
# other local processes that can reach localhost.
_LOCAL_TOKEN: str = secrets.token_urlsafe(32)
_LOCAL_ADDRS = frozenset({"127.0.0.1", "::1", "localhost"})


def _require_local() -> None:
    if request.remote_addr not in _LOCAL_ADDRS:
        abort(403, "cloud-sync endpoints are local-only")


@bp.before_request
def _check_token() -> Any:
    # Bootstrap endpoint is exempt; it's what the UI uses to fetch the token.
    if request.endpoint and request.endpoint.endswith(".get_bootstrap_token"):
        return None
    _require_local()
    supplied = request.headers.get("X-Cloud-Sync-Token", "")
    if not supplied or not secrets.compare_digest(supplied, _LOCAL_TOKEN):
        abort(403, "missing or invalid X-Cloud-Sync-Token")
    return None


@bp.get("/bootstrap-token")
def get_bootstrap_token():
    """Return the per-process token to same-origin local callers.

    The dashboard JS fetches this once on load and attaches the result to every
    subsequent request. Non-local callers get 403.
    """
    _require_local()
    return jsonify({"token": _LOCAL_TOKEN})


# Keys accepted on POST /config. Missing keys mean "no change".
_POSTABLE_KEYS: tuple[str, ...] = (
    K_PROVIDER, K_ROOT_PREFIX,
    K_R2_ACCOUNT_ID, K_R2_ACCESS_KEY_ID, K_R2_SECRET_ACCESS_KEY,
    K_R2_BUCKET, K_R2_ENDPOINT_URL,
    K_S3_ACCESS_KEY_ID, K_S3_SECRET_ACCESS_KEY,
    K_S3_BUCKET, K_S3_REGION, K_S3_ENDPOINT_URL,
    K_AZ_ACCOUNT, K_AZ_KEY, K_AZ_CONTAINER, K_AZ_ENDPOINT_SUFFIX,
)


@bp.get("/config")
def get_config():
    if not env_exists():
        return jsonify({
            "configured": False,
            "env_path": str(ENV_PATH),
            "default_root_prefix": DEFAULT_ROOT_PREFIX,
            "providers": [p.value for p in ProviderType],
        })
    try:
        settings = load_settings()
    except CredentialError as e:
        return jsonify({"configured": False, "error": str(e)}), 400
    return jsonify({
        "configured": True,
        "env_path": str(ENV_PATH),
        "settings": settings.masked(),
    })


@bp.post("/config")
def post_config():
    payload = request.get_json(silent=True) or {}
    values: dict[str, str] = {}
    for k in _POSTABLE_KEYS:
        v = payload.get(k)
        if v is None:
            continue
        if not isinstance(v, str):
            v = str(v)
        values[k] = v
    ensure_home()
    save_env(values)
    fix_perms()
    check_not_in_git()
    try:
        settings = load_settings()
    except CredentialError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "settings": settings.masked()})


@bp.post("/test")
def post_test():
    try:
        settings = _load()
    except CredentialError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    provider = build_provider(settings)
    import socket
    import time

    probe_key = (
        f"{settings.root_prefix.rstrip('/')}/.self-test/"
        f"{int(time.time())}-{socket.gethostname()}"
    )
    body = f"serena cloud-sync dashboard probe {time.time()}".encode("utf-8")
    sha = sha256_bytes(body)
    try:
        provider.put_object_if_absent(probe_key, body, sha)
        got = provider.get_object(probe_key)
        provider.delete_object(probe_key)
        return jsonify({"ok": True, "round_trip_ok": got == body, "probe_key": probe_key})
    except CloudSyncError as e:
        return jsonify({"ok": False, "error": str(e), "probe_key": probe_key}), 500
    finally:
        provider.close()


@bp.get("/status")
def get_status():
    try:
        settings = _load()
    except CredentialError as e:
        return jsonify({"configured": False, "error": str(e)}), 400
    include_local = _flag(request.args.get("include_project_local_yml"))
    service, roots_info = _build_service(settings, include_local)
    local, remote, diff = service.build_plan()
    return jsonify({
        "provider": settings.provider.value,
        "root_prefix": settings.root_prefix,
        "roots": roots_info,
        "local_count": len(local),
        "remote_count": len(remote),
        "plan_counts": diff.counts(),
    })


@bp.post("/push")
def post_push():
    return _run("push")


@bp.post("/pull")
def post_pull():
    return _run("pull")


def _run(mode: str):
    try:
        settings = _load()
    except CredentialError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    body = request.get_json(silent=True) or {}
    dry_run = bool(body.get("dry_run", True))  # UI default is dry-run-first
    force = bool(body.get("force", False))
    byte_compare = bool(body.get("byte_compare", False))
    include_local = bool(body.get("include_project_local_yml", False))
    service, _ = _build_service(settings, include_local)
    report: SyncReport
    if mode == "push":
        report = service.push(dry_run=dry_run, force=force, byte_compare=byte_compare)
    else:
        report = service.pull(dry_run=dry_run, force=force, byte_compare=byte_compare)
    return jsonify({"ok": True, "report": report.to_dict()})


def _load() -> CloudSyncSettings:
    settings = load_settings()
    install_redactor(log, settings)
    install_redactor(logging.getLogger("serena.cloud_sync"), settings)
    return settings


def _build_service(settings: CloudSyncSettings, include_local_yml: bool):
    # Dashboard process is long-running; we discover roots from the server cwd.
    from serena.cloud_sync.cli import _discover_project_roots
    roots = _discover_project_roots()
    scope = ScopeFilter(
        include_patterns=tuple(list(DEFAULT_GLOBAL_INCLUDES) + list(DEFAULT_PROJECT_INCLUDES)),
        opt_in_project_local_yml=include_local_yml,
    )
    progress_path = Path(str(ENV_PATH.parent / "cloud-sync.progress.json"))
    service = CloudSyncService(
        provider=build_provider(settings),
        scope=scope,
        roots=roots,
        root_prefix=settings.root_prefix,
        progress_path=progress_path,
    )
    roots_info = [{"path": str(r.local_root), "remote_subprefix": r.remote_subprefix} for r in roots]
    return service, roots_info


def _flag(v: Any) -> bool:
    return str(v or "").lower() in ("1", "true", "yes", "on")
