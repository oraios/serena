"""Tests for the experimental EmmyLua Analyzer Rust backend."""

import platform
from pathlib import Path
from unittest.mock import patch

import pytest

from solidlsp.language_servers.emmylua_ls import (
    DEFAULT_EMMYLUA_LS_VERSION,
    EMMYLUA_ALLOWED_HOSTS,
    EmmyLuaLanguageServer,
    _emmylua_ls_asset,
    _emmylua_ls_dep,
    _emmylua_ls_install_dir,
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


@pytest.mark.parametrize(
    ("system", "machine"),
    [("Linux", "x86_64"), ("Linux", "aarch64"), ("Darwin", "x86_64"), ("Darwin", "arm64"), ("Windows", "amd64"), ("Windows", "arm64")],
)
def test_pinned_release_assets_are_checksum_verified(tmp_path: Path, system: str, machine: str) -> None:
    dep = _emmylua_ls_dep(system, machine)

    with patch("solidlsp.dependency_provider.FileUtils.download_and_extract_archive_verified") as download:
        dep.download_to(tmp_path)

    assert download.call_args.kwargs["expected_sha256"] is not None, "pinned release must be verified against the hash database"


def test_custom_versions_skip_hash_lookup_by_design(tmp_path: Path) -> None:
    dep = _emmylua_ls_dep("Linux", "x86_64", "0.26.0")

    with (
        patch(
            "solidlsp.dependency_provider.DownloadedDependencyHashDatabase.get_instance",
            side_effect=AssertionError("custom versions must not consult the pinned hash database"),
        ),
        patch("solidlsp.dependency_provider.FileUtils.download_and_extract_archive_verified") as download,
    ):
        dep.download_to(tmp_path)

    download.assert_called_once_with(
        "https://github.com/EmmyLuaLs/emmylua-analyzer-rust/releases/download/0.26.0/emmylua_ls-linux-x64-glibc.2.17.tar.gz",
        str(tmp_path),
        archive_type="gztar",
        expected_sha256=None,
        allowed_hosts=EMMYLUA_ALLOWED_HOSTS,
    )


def test_install_dir_is_versioned_after_initial_release(tmp_path: Path) -> None:
    assert _emmylua_ls_install_dir(str(tmp_path), DEFAULT_EMMYLUA_LS_VERSION) == tmp_path / "emmylua"
    assert _emmylua_ls_install_dir(str(tmp_path), "0.26.0") == tmp_path / "emmylua-0.26.0"


def test_ls_path_override_is_used_without_downloading(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path, {"ls_path": "/opt/emmylua_ls"})
    with patch.object(
        EmmyLuaLanguageServer,
        "_download_emmylua_ls",
        side_effect=AssertionError("download should not be attempted"),
    ):
        assert EmmyLuaLanguageServer._setup_runtime_dependency(settings) == "/opt/emmylua_ls"


def test_managed_binary_is_reused(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    binary_name = "emmylua_ls.exe" if platform.system() == "Windows" else "emmylua_ls"
    managed_path = Path(EmmyLuaLanguageServer.ls_resources_dir(settings)) / "emmylua" / binary_name
    managed_path.parent.mkdir(parents=True)
    managed_path.write_text("binary", encoding="utf-8")
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
        assert expected_sha256 is not None
        assert allowed_hosts is not None
        Path(target_path, "emmylua_ls").write_text("#!/bin/sh\n", encoding="utf-8")

    with patch("solidlsp.language_servers.emmylua_ls.platform.system", return_value="Linux"):
        with patch("solidlsp.language_servers.emmylua_ls.platform.machine", return_value="x86_64"):
            with patch(
                "solidlsp.dependency_provider.FileUtils.download_and_extract_archive_verified",
                side_effect=fake_extract,
            ):
                binary_path = EmmyLuaLanguageServer._download_emmylua_ls(settings)

    resolved_path = Path(binary_path)
    assert resolved_path == Path(EmmyLuaLanguageServer.ls_resources_dir(settings)) / "emmylua" / "emmylua_ls"
    if platform.system() != "Windows":
        assert resolved_path.stat().st_mode & 0o111


def test_language_server_id_registers_emmylua_as_experimental() -> None:
    language_server_id = LanguageServerId.LUA_EMMYLUA
    assert language_server_id.is_experimental()
    assert language_server_id.get_source_fn_matcher().is_relevant_filename("module.lua")
    assert language_server_id.get_ls_class() is EmmyLuaLanguageServer
