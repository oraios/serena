"""Tests for the dependency handling and registration of the experimental EmmyLua Analyzer backend."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from solidlsp.language_servers.emmylua_ls import (
    DEFAULT_EMMYLUA_LS_VERSION,
    EMMYLUA_LS_ALLOWED_HOSTS,
    EMMYLUA_LS_ASSET_BY_PLATFORM_ID,
    EmmyLuaLanguageServer,
)
from solidlsp.ls_config import LanguageServerId
from solidlsp.ls_utils import PlatformId
from solidlsp.settings import SolidLSPSettings

RELEASE_URL = "https://github.com/EmmyLuaLs/emmylua-analyzer-rust/releases/download"


def _make_provider(tmp_path: Path, custom_settings: dict[str, str] | None = None) -> EmmyLuaLanguageServer.DependencyProvider:
    return EmmyLuaLanguageServer.DependencyProvider(
        custom_settings=SolidLSPSettings.CustomLSSettings(custom_settings or {}),
        ls_resources_dir=str(tmp_path),
    )


@pytest.mark.lua
class TestEmmyLuaDependencyProvider:
    @pytest.mark.parametrize(
        ("platform_id", "asset_name", "archive_type"),
        [
            (PlatformId.LINUX_x64, "emmylua_ls-linux-x64-glibc.2.17.tar.gz", "gztar"),
            (PlatformId.LINUX_arm64, "emmylua_ls-linux-aarch64-glibc.2.17.tar.gz", "gztar"),
            (PlatformId.OSX_x64, "emmylua_ls-darwin-x64.tar.gz", "gztar"),
            (PlatformId.OSX_arm64, "emmylua_ls-darwin-arm64.tar.gz", "gztar"),
            (PlatformId.WIN_x64, "emmylua_ls-win32-x64.zip", "zip"),
            (PlatformId.WIN_arm64, "emmylua_ls-win32-arm64.zip", "zip"),
        ],
    )
    def test_asset_mapping(self, platform_id: PlatformId, asset_name: str, archive_type: str) -> None:
        assert EMMYLUA_LS_ASSET_BY_PLATFORM_ID[platform_id] == (asset_name, archive_type)
        dep = EmmyLuaLanguageServer.DependencyProvider._create_dep_emmylua_ls(platform_id)
        assert dep.get_url() == f"{RELEASE_URL}/{DEFAULT_EMMYLUA_LS_VERSION}/{asset_name}"

    @pytest.mark.parametrize("platform_id", list(EMMYLUA_LS_ASSET_BY_PLATFORM_ID))
    def test_pinned_release_assets_are_checksum_verified(self, tmp_path: Path, platform_id: PlatformId) -> None:
        dep = EmmyLuaLanguageServer.DependencyProvider._create_dep_emmylua_ls(platform_id)

        with patch("solidlsp.dependency_provider.FileUtils.download_and_extract_archive_verified") as download:
            dep.download_to(tmp_path)

        assert download.call_args.kwargs["expected_sha256"] is not None, "pinned release must be verified against the hash database"

    def test_custom_versions_skip_hash_lookup_by_design(self, tmp_path: Path) -> None:
        dep = EmmyLuaLanguageServer.DependencyProvider._create_dep_emmylua_ls(PlatformId.LINUX_x64, "0.26.0")

        with (
            patch(
                "solidlsp.dependency_provider.DownloadedDependencyHashDatabase.get_instance",
                side_effect=AssertionError("custom versions must not consult the pinned hash database"),
            ),
            patch("solidlsp.dependency_provider.FileUtils.download_and_extract_archive_verified") as download,
        ):
            dep.download_to(tmp_path)

        download.assert_called_once_with(
            f"{RELEASE_URL}/0.26.0/emmylua_ls-linux-x64-glibc.2.17.tar.gz",
            str(tmp_path),
            archive_type="gztar",
            expected_sha256=None,
            allowed_hosts=EMMYLUA_LS_ALLOWED_HOSTS,
        )

    def test_ls_path_override_is_used_without_downloading(self, tmp_path: Path) -> None:
        provider = _make_provider(tmp_path, {"ls_path": "/opt/emmylua_ls"})

        with patch.object(
            EmmyLuaLanguageServer.DependencyProvider,
            "_get_or_install_core_dependency",
            side_effect=AssertionError("the managed installation must not be used when ls_path is set"),
        ):
            assert provider.create_launch_command() == ["/opt/emmylua_ls"]

    @pytest.mark.parametrize(
        ("platform_id", "executable_name"),
        [(PlatformId.LINUX_x64, "emmylua_ls"), (PlatformId.OSX_arm64, "emmylua_ls"), (PlatformId.WIN_x64, "emmylua_ls.exe")],
    )
    def test_managed_binary_is_reused(self, tmp_path: Path, platform_id: PlatformId, executable_name: str) -> None:
        install_dir = tmp_path / f"emmylua_ls-{DEFAULT_EMMYLUA_LS_VERSION}-{platform_id.value}"
        install_dir.mkdir()
        executable = install_dir / executable_name
        executable.write_text("binary", encoding="utf-8")

        with (
            patch("solidlsp.language_servers.emmylua_ls.PlatformUtils.get_platform_id", return_value=platform_id),
            patch("solidlsp.dependency_provider.FileUtils.download_and_extract_archive_verified") as download,
        ):
            assert _make_provider(tmp_path).create_launch_command() == [str(executable)]

        download.assert_not_called()

    def test_download_extracts_binary_into_versioned_install_dir(self, tmp_path: Path) -> None:
        def fake_extract(
            url: str, target_path: str, archive_type: str, expected_sha256: str | None, allowed_hosts: tuple[str, ...]
        ) -> None:
            assert url == f"{RELEASE_URL}/{DEFAULT_EMMYLUA_LS_VERSION}/emmylua_ls-linux-x64-glibc.2.17.tar.gz"
            assert archive_type == "gztar"
            assert expected_sha256 is not None
            assert allowed_hosts == EMMYLUA_LS_ALLOWED_HOSTS
            Path(target_path, "emmylua_ls").write_text("#!/bin/sh\n", encoding="utf-8")

        with (
            patch("solidlsp.language_servers.emmylua_ls.PlatformUtils.get_platform_id", return_value=PlatformId.LINUX_x64),
            patch("solidlsp.dependency_provider.FileUtils.download_and_extract_archive_verified", side_effect=fake_extract),
        ):
            (executable,) = _make_provider(tmp_path).create_launch_command()

        assert Path(executable) == tmp_path / f"emmylua_ls-{DEFAULT_EMMYLUA_LS_VERSION}-linux-x64" / "emmylua_ls"
        assert os.access(executable, os.X_OK)

    def test_custom_version_uses_its_own_install_dir(self, tmp_path: Path) -> None:
        def fake_extract(
            url: str, target_path: str, archive_type: str, expected_sha256: str | None, allowed_hosts: tuple[str, ...]
        ) -> None:
            assert "/0.26.0/" in url
            assert expected_sha256 is None
            Path(target_path, "emmylua_ls").write_text("#!/bin/sh\n", encoding="utf-8")

        provider = _make_provider(tmp_path, {"emmylua_ls_version": "0.26.0"})
        with (
            patch("solidlsp.language_servers.emmylua_ls.PlatformUtils.get_platform_id", return_value=PlatformId.LINUX_x64),
            patch("solidlsp.dependency_provider.FileUtils.download_and_extract_archive_verified", side_effect=fake_extract),
        ):
            (executable,) = provider.create_launch_command()

        assert Path(executable) == tmp_path / "emmylua_ls-0.26.0-linux-x64" / "emmylua_ls"

    def test_missing_binary_after_installation_is_reported(self, tmp_path: Path) -> None:
        with (
            patch("solidlsp.language_servers.emmylua_ls.PlatformUtils.get_platform_id", return_value=PlatformId.LINUX_x64),
            patch("solidlsp.dependency_provider.FileUtils.download_and_extract_archive_verified"),
            pytest.raises(FileNotFoundError, match="emmylua_ls executable not found"),
        ):
            _make_provider(tmp_path).create_launch_command()

    def test_unsupported_platform_is_rejected(self, tmp_path: Path) -> None:
        with (
            patch("solidlsp.language_servers.emmylua_ls.PlatformUtils.get_platform_id", return_value=PlatformId.LINUX_MUSL_x64),
            pytest.raises(RuntimeError, match="not available for platform linux-musl-x64"),
        ):
            _make_provider(tmp_path).create_launch_command()


@pytest.mark.lua
def test_language_server_id_registers_emmylua_as_experimental() -> None:
    language_server_id = LanguageServerId.LUA_EMMYLUA
    assert language_server_id.is_experimental()
    assert language_server_id.get_source_fn_matcher().is_relevant_filename("module.lua")
    assert language_server_id.get_ls_class() is EmmyLuaLanguageServer
