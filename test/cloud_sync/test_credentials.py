import os
import stat
from pathlib import Path

import pytest

from serena.cloud_sync import credentials as creds
from serena.cloud_sync.exceptions import CredentialError


@pytest.fixture
def tmp_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the module-level env_path to a tmp location."""
    env_path = tmp_path / "cloud-sync.env"
    monkeypatch.setattr(creds, "ENV_PATH", env_path)
    monkeypatch.setattr(creds, "ENV_BACKUP_PATH", env_path.parent / (env_path.name + ".bak"))
    monkeypatch.setattr(creds, "SERENA_HOME", tmp_path)
    return env_path


def test_save_and_reload_r2(tmp_env: Path) -> None:
    creds.save_env({
        creds.K_PROVIDER: "r2",
        creds.K_R2_ACCOUNT_ID: "abc123",
        creds.K_R2_ACCESS_KEY_ID: "AKID",
        creds.K_R2_SECRET_ACCESS_KEY: "s3cr3t",
        creds.K_R2_BUCKET: "my-bucket",
    }, path=tmp_env)
    s = creds.load_settings(path=tmp_env)
    assert s.provider.value == "r2"
    assert s.r2 is not None
    assert s.r2.secret_access_key == "s3cr3t"
    # File must be 0600 on POSIX
    if os.name == "posix":
        mode = stat.S_IMODE(tmp_env.stat().st_mode)
        assert mode == 0o600


def test_perms_warning_raises(tmp_env: Path) -> None:
    creds.save_env({
        creds.K_PROVIDER: "r2",
        creds.K_R2_ACCOUNT_ID: "x", creds.K_R2_ACCESS_KEY_ID: "x",
        creds.K_R2_SECRET_ACCESS_KEY: "x", creds.K_R2_BUCKET: "x",
    }, path=tmp_env)
    if os.name == "posix":
        os.chmod(tmp_env, 0o644)
        with pytest.raises(CredentialError):
            creds.check_perms(tmp_env)


def test_mask_sentinel_preserves_existing_secret(tmp_env: Path) -> None:
    creds.save_env({
        creds.K_PROVIDER: "r2",
        creds.K_R2_ACCOUNT_ID: "x", creds.K_R2_ACCESS_KEY_ID: "AKID",
        creds.K_R2_SECRET_ACCESS_KEY: "REAL-SECRET",
        creds.K_R2_BUCKET: "x",
    }, path=tmp_env)
    # Second save: secret passed as '****' must not overwrite
    creds.save_env({
        creds.K_R2_SECRET_ACCESS_KEY: "****",
        creds.K_R2_BUCKET: "new-bucket",
    }, path=tmp_env)
    s = creds.load_settings(path=tmp_env)
    assert s.r2 is not None
    assert s.r2.secret_access_key == "REAL-SECRET"
    assert s.r2.bucket == "new-bucket"


def test_missing_file_raises(tmp_env: Path) -> None:
    with pytest.raises(CredentialError):
        creds.load_settings(path=tmp_env)
