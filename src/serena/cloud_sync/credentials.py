"""Dotenv-based credential store with chmod-600 atomic writes.

Single file ``~/.serena/cloud-sync.env`` with provider-prefixed keys; never
inlined in any YAML that could be committed.
"""
from __future__ import annotations

import logging
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

from dotenv import dotenv_values

from serena.cloud_sync.exceptions import CredentialError
from serena.cloud_sync.settings import (
    AzureSettings,
    CloudSyncSettings,
    DEFAULT_ROOT_PREFIX,
    ProviderType,
    R2Settings,
    S3Settings,
)

log = logging.getLogger(__name__)

ENV_FILENAME = "cloud-sync.env"
SERENA_HOME = Path(os.environ.get("SERENA_HOME", os.path.expanduser("~/.serena"))).resolve()
ENV_PATH = SERENA_HOME / ENV_FILENAME
ENV_BACKUP_PATH = SERENA_HOME / (ENV_FILENAME + ".bak")

# Keys we read from the env file.
K_PROVIDER = "CLOUD_SYNC_PROVIDER"
K_ROOT_PREFIX = "CLOUD_SYNC_ROOT_PREFIX"

# R2
K_R2_ACCOUNT_ID = "R2_ACCOUNT_ID"
K_R2_ACCESS_KEY_ID = "R2_ACCESS_KEY_ID"
K_R2_SECRET_ACCESS_KEY = "R2_SECRET_ACCESS_KEY"
K_R2_BUCKET = "R2_BUCKET"
K_R2_ENDPOINT_URL = "R2_ENDPOINT_URL"

# S3
K_S3_ACCESS_KEY_ID = "AWS_ACCESS_KEY_ID"
K_S3_SECRET_ACCESS_KEY = "AWS_SECRET_ACCESS_KEY"
K_S3_BUCKET = "AWS_BUCKET"
K_S3_REGION = "AWS_REGION"
K_S3_ENDPOINT_URL = "AWS_ENDPOINT_URL"

# Azure
K_AZ_ACCOUNT = "AZURE_STORAGE_ACCOUNT"
K_AZ_KEY = "AZURE_STORAGE_ACCOUNT_KEY"
K_AZ_CONTAINER = "AZURE_CONTAINER"
K_AZ_ENDPOINT_SUFFIX = "AZURE_ENDPOINT_SUFFIX"

SECRET_KEYS: frozenset[str] = frozenset({
    K_R2_SECRET_ACCESS_KEY,
    K_S3_SECRET_ACCESS_KEY,
    K_AZ_KEY,
})


def env_path() -> Path:
    return ENV_PATH


def ensure_home() -> None:
    SERENA_HOME.mkdir(parents=True, exist_ok=True)


def env_exists() -> bool:
    return ENV_PATH.is_file()


def check_perms(path: Path = ENV_PATH) -> None:
    """Raise CredentialError if perms are wider than 0600 on a POSIX filesystem."""
    if os.name != "posix":
        return
    if not path.exists():
        return
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise CredentialError(
            f"credentials file {path} has mode 0{mode:o}; must be 0600. "
            f"Run: serena cloud-sync fix-perms"
        )


def fix_perms(path: Path = ENV_PATH) -> None:
    if os.name != "posix":
        return
    if not path.exists():
        return
    os.chmod(path, 0o600)


def check_not_in_git(path: Path = ENV_PATH) -> None:
    """Loud warning (not a hard error) if the env file sits inside a git repo.

    We check with ``git rev-parse --show-toplevel``. Silent if git is absent.
    """
    if not path.exists():
        return
    try:
        res = subprocess.run(
            ["git", "-C", str(path.parent), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, timeout=3,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return
    if res.returncode == 0 and res.stdout.strip() == "true":
        log.warning(
            "cloud-sync credentials file at %s is inside a git working tree; "
            "make sure it is .gitignore'd before committing anything", path
        )


def load_settings(path: Path = ENV_PATH) -> CloudSyncSettings:
    """Load settings from the env file. Raises CredentialError if file missing
    or if the active provider's required keys are absent."""
    if not path.exists():
        raise CredentialError(
            f"no cloud-sync credentials at {path}; run `serena cloud-sync configure`"
        )
    check_perms(path)
    raw = dotenv_values(path)

    provider_value = (raw.get(K_PROVIDER) or "").strip().lower()
    if not provider_value:
        raise CredentialError(f"{K_PROVIDER} not set in {path}")
    try:
        provider = ProviderType(provider_value)
    except ValueError as e:
        raise CredentialError(
            f"{K_PROVIDER}={provider_value!r} is not one of {[p.value for p in ProviderType]}"
        ) from e

    root_prefix = (raw.get(K_ROOT_PREFIX) or DEFAULT_ROOT_PREFIX).strip() or DEFAULT_ROOT_PREFIX

    r2 = _parse_r2(raw)
    s3 = _parse_s3(raw)
    az = _parse_azure(raw)

    settings = CloudSyncSettings(
        provider=provider,
        root_prefix=root_prefix,
        r2=r2,
        s3=s3,
        azure=az,
    )
    # Validate active provider is populated (raises a clear error otherwise)
    settings.active_provider_settings()
    return settings


def _parse_r2(raw: dict[str, str | None]) -> R2Settings | None:
    acc = raw.get(K_R2_ACCOUNT_ID)
    akid = raw.get(K_R2_ACCESS_KEY_ID)
    sk = raw.get(K_R2_SECRET_ACCESS_KEY)
    bucket = raw.get(K_R2_BUCKET)
    if not any((acc, akid, sk, bucket)):
        return None
    if not (acc and akid and sk and bucket):
        raise CredentialError("R2 settings partially configured; fill all of R2_ACCOUNT_ID/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY/R2_BUCKET")
    return R2Settings(
        account_id=acc, access_key_id=akid, secret_access_key=sk,
        bucket=bucket, endpoint_url=raw.get(K_R2_ENDPOINT_URL) or None,
    )


def _parse_s3(raw: dict[str, str | None]) -> S3Settings | None:
    akid = raw.get(K_S3_ACCESS_KEY_ID)
    sk = raw.get(K_S3_SECRET_ACCESS_KEY)
    bucket = raw.get(K_S3_BUCKET)
    if not any((akid, sk, bucket)):
        return None
    if not (akid and sk and bucket):
        raise CredentialError("S3 settings partially configured; fill AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY/AWS_BUCKET")
    return S3Settings(
        access_key_id=akid, secret_access_key=sk, bucket=bucket,
        region=raw.get(K_S3_REGION) or "us-east-1",
        endpoint_url=raw.get(K_S3_ENDPOINT_URL) or None,
    )


def _parse_azure(raw: dict[str, str | None]) -> AzureSettings | None:
    acct = raw.get(K_AZ_ACCOUNT)
    key = raw.get(K_AZ_KEY)
    container = raw.get(K_AZ_CONTAINER)
    if not any((acct, key, container)):
        return None
    if not (acct and key and container):
        raise CredentialError("Azure settings partially configured; fill AZURE_STORAGE_ACCOUNT/AZURE_STORAGE_ACCOUNT_KEY/AZURE_CONTAINER")
    return AzureSettings(
        account_name=acct, account_key=key, container=container,
        endpoint_suffix=raw.get(K_AZ_ENDPOINT_SUFFIX) or "core.windows.net",
    )


def save_env(values: dict[str, str], path: Path = ENV_PATH) -> None:
    """Atomically write the env file and chmod it 0600.

    ``values`` with value ``'****'`` are treated as 'unchanged' and preserved
    from the existing file on disk.
    """
    ensure_home()
    existing: dict[str, str] = {}
    if path.exists():
        check_perms(path)
        existing = {k: v or "" for k, v in dotenv_values(path).items()}
        shutil.copy2(path, ENV_BACKUP_PATH)
        if os.name == "posix":
            os.chmod(ENV_BACKUP_PATH, 0o600)

    # Merge: keep previous secrets when the incoming value is the mask sentinel.
    merged: dict[str, str] = dict(existing)
    for k, v in values.items():
        if v is None:
            continue
        if v == "****":
            continue  # keep existing (or leave absent)
        merged[k] = v

    # Atomic write.
    tmp = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=str(path.parent), delete=False,
    )
    try:
        for k in sorted(merged.keys()):
            v = merged[k]
            # quote values that contain whitespace or special chars
            if any(c in v for c in " \t#\"'`$"):
                v = '"' + v.replace('\\', '\\\\').replace('"', '\\"') + '"'
            tmp.write(f"{k}={v}\n")
        tmp.flush()
        os.fsync(tmp.fileno())
    finally:
        tmp.close()
    os.replace(tmp.name, path)
    if os.name == "posix":
        os.chmod(path, 0o600)


class SecretRedactingFilter(logging.Filter):
    """Redact any SECRET_KEYS values from log records.

    Installed on the cloud-sync logger. Defence-in-depth against accidental
    ``repr(settings)`` or SDK traceback leaks.
    """

    def __init__(self, secret_values: frozenset[str] | None = None) -> None:
        super().__init__()
        self._secret_values = frozenset(v for v in (secret_values or frozenset()) if v)

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        redacted = msg
        for sv in self._secret_values:
            if sv and sv in redacted:
                redacted = redacted.replace(sv, "****REDACTED****")
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


def install_redactor(logger: logging.Logger, settings: CloudSyncSettings) -> None:
    """Attach a SecretRedactingFilter derived from settings onto ``logger``."""
    secrets = set()
    if settings.r2:
        secrets.add(settings.r2.secret_access_key)
    if settings.s3:
        secrets.add(settings.s3.secret_access_key)
    if settings.azure:
        secrets.add(settings.azure.account_key)
    logger.addFilter(SecretRedactingFilter(frozenset(secrets)))
