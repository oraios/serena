"""Tests for the experimental EmmyLua Analyzer Rust backend."""

from pathlib import Path
from unittest.mock import patch

import pytest

from solidlsp.language_servers.emmylua_ls import (
    DEFAULT_EMMYLUA_LS_VERSION,
    EmmyLuaLanguageServer,
    _emmylua_ls_asset,
    _emmylua_ls_install_dir,
    _emmylua_ls_sha,
)
from solidlsp.ls_config import LanguageServerId
from solidlsp.settings import SolidLSPSettings


def _make_settings(tmp_path: Path, custom_settings: dict[str, str] | None = None) -> SolidLSPSettings:
    return SolidLSPSettings(
        solidlsp_dir=str(tmp_path),
        ls_specific_settings={LanguageServerId.LUA_EMMYLUA: custom_settings or {}},
    )


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("Linux", "x86_64", ("emmylua_ls-linux-x64-glibc.2.17.tar.gz", "gztar", "emmylua_ls")),
        ("Linux", "aarch64", ("emmylua_ls-linux-aarch64-glibc.2.17.tar.gz", "gztar", "emmylua_ls")),
        ("Darwin", "arm64", ("emmylua_ls-darwin-arm64.tar.gz", "gztar", "emmylua_ls")),
        ("Windows", "AMD64", ("emmylua_ls-win32-x64.zip", "zip", "emmylua_ls.exe")),
        ("Windows", "arm64", ("emmylua_ls-win32-arm64.zip", "zip", "emmylua_ls.exe")),
    ],
)
def test_asset_mapping(system: str, machine: str, expected: tuple[str, str, str]) -> None:
    assert _emmylua_ls_asset(system, machine) == expected


def test_asset_mapping_rejects_unsupported_platform() -> None:
    with pytest.raises(RuntimeError, match="Unsupported Linux architecture"):
        _emmylua_ls_asset("Linux", "i686")


def test_default_release_assets_have_sha256() -> None:
    for system, machine in (("Linux", "x86_64"), ("Linux", "aarch64"), ("Darwin", "x86_64"), ("Windows", "amd64")):
        asset_name, _, _ = _emmylua_ls_asset(system, machine)
        digest = _emmylua_ls_sha(DEFAULT_EMMYLUA_LS_VERSION, asset_name)
        assert digest is not None
        assert len(digest) == 64


def test_install_dir_is_versioned_after_initial_release(tmp_path: Path) -> None:
    assert _emmylua_ls_install_dir(str(tmp_path), DEFAULT_EMMYLUA_LS_VERSION) == tmp_path / "emmylua"
    assert _emmylua_ls_install_dir(str(tmp_path), "0.26.0") == tmp_path / "emmylua-0.26.0"


def test_ls_path_override_is_used_without_looking_at_path_or_downloading(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path, {"ls_path": "/opt/emmylua_ls"})
    with patch("solidlsp.language_servers.emmylua_ls.shutil.which", side_effect=AssertionError("PATH should not be checked")):
        with patch.object(
            EmmyLuaLanguageServer,
            "_download_emmylua_ls",
            side_effect=AssertionError("download should not be attempted"),
        ):
            assert EmmyLuaLanguageServer._setup_runtime_dependency(settings) == "/opt/emmylua_ls"


def test_system_binary_is_preferred_to_managed_install(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    with patch("solidlsp.language_servers.emmylua_ls.shutil.which", return_value="/usr/bin/emmylua_ls"):
        with patch.object(
            EmmyLuaLanguageServer,
            "_download_emmylua_ls",
            side_effect=AssertionError("download should not be attempted"),
        ):
            assert EmmyLuaLanguageServer._setup_runtime_dependency(settings) == "/usr/bin/emmylua_ls"


def test_managed_binary_is_reused(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    managed_path = Path(EmmyLuaLanguageServer.ls_resources_dir(settings)) / "emmylua" / "emmylua_ls"
    managed_path.parent.mkdir(parents=True)
    managed_path.write_text("binary", encoding="utf-8")
    with patch("solidlsp.language_servers.emmylua_ls.shutil.which", return_value=None):
        with patch.object(
            EmmyLuaLanguageServer,
            "_download_emmylua_ls",
            side_effect=AssertionError("download should not be attempted"),
        ):
            assert EmmyLuaLanguageServer._setup_runtime_dependency(settings) == str(managed_path)


def test_download_extracts_and_returns_binary(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)

    def fake_extract(
        url: str,
        target_path: str,
        archive_type: str,
        expected_sha256: str | None = None,
        allowed_hosts: tuple[str, ...] | list[str] | None = None,
    ) -> None:
        assert url.endswith("emmylua_ls-linux-x64-glibc.2.17.tar.gz")
        assert archive_type == "gztar"
        assert expected_sha256 == _emmylua_ls_sha(DEFAULT_EMMYLUA_LS_VERSION, "emmylua_ls-linux-x64-glibc.2.17.tar.gz")
        assert allowed_hosts is not None
        Path(target_path, "emmylua_ls").write_text("#!/bin/sh\n", encoding="utf-8")

    with patch("solidlsp.language_servers.emmylua_ls.platform.system", return_value="Linux"):
        with patch("solidlsp.language_servers.emmylua_ls.platform.machine", return_value="x86_64"):
            with patch(
                "solidlsp.language_servers.emmylua_ls.FileUtils.download_and_extract_archive_verified",
                side_effect=fake_extract,
            ):
                binary_path = EmmyLuaLanguageServer._download_emmylua_ls(settings)

    resolved_path = Path(binary_path)
    assert resolved_path == Path(EmmyLuaLanguageServer.ls_resources_dir(settings)) / "emmylua" / "emmylua_ls"
    assert resolved_path.stat().st_mode & 0o111


def test_language_server_id_registers_emmylua_as_experimental() -> None:
    language_server_id = LanguageServerId.LUA_EMMYLUA
    assert language_server_id.is_experimental()
    assert language_server_id.get_source_fn_matcher().is_relevant_filename("module.lua")
    assert language_server_id.get_ls_class() is EmmyLuaLanguageServer
