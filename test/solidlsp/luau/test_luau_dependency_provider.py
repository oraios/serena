"""Tests for the Luau language server dependency provider."""

from pathlib import Path
from unittest.mock import patch

import pytest

from solidlsp.language_servers.luau_lsp import LuauLanguageServer
from solidlsp.settings import SolidLSPSettings


def _make_provider(
    tmp_path: Path,
    custom_settings: dict[str, str] | None = None,
) -> LuauLanguageServer.DependencyProvider:
    return LuauLanguageServer.DependencyProvider(
        custom_settings=SolidLSPSettings.CustomLSSettings(custom_settings or {}),
        ls_resources_dir=str(tmp_path),
    )


@pytest.mark.luau
class TestLuauDependencyProvider:
    def test_create_launch_command_uses_ls_path_override_and_adds_assets(self, tmp_path: Path) -> None:
        provider = _make_provider(tmp_path, {"ls_path": "/custom/luau-lsp"})

        with patch.object(
            provider,
            "_get_or_install_core_dependency",
            side_effect=AssertionError("_get_or_install_core_dependency should not be called when ls_path is set"),
        ):
            with patch.object(
                provider,
                "_resolve_support_files",
                return_value=("/tmp/globalTypes.d.luau", "/tmp/en-us.json"),
            ):
                assert provider.create_launch_command() == [
                    "/custom/luau-lsp",
                    "lsp",
                    "--definitions:@roblox=/tmp/globalTypes.d.luau",
                    "--docs=/tmp/en-us.json",
                ]

    def test_resolve_support_files_defaults_to_roblox_mode(self, tmp_path: Path) -> None:
        provider = _make_provider(tmp_path)

        with patch.object(
            provider,
            "_download_roblox_support_files",
            return_value=("/tmp/globalTypes.PluginSecurity.d.luau", "/tmp/en-us.json"),
        ) as download_roblox_support_files:
            with patch.object(
                provider,
                "_download_standard_docs",
                side_effect=AssertionError("_download_standard_docs should not be called in roblox mode"),
            ):
                assert provider._resolve_support_files() == (
                    "/tmp/globalTypes.PluginSecurity.d.luau",
                    "/tmp/en-us.json",
                )

        download_roblox_support_files.assert_called_once_with("PluginSecurity")

    def test_resolve_support_files_uses_standard_mode_docs_only(self, tmp_path: Path) -> None:
        provider = _make_provider(tmp_path, {"platform": "standard"})

        with patch.object(provider, "_download_standard_docs", return_value="/tmp/luau-en-us.json") as download_standard_docs:
            with patch.object(
                provider,
                "_download_roblox_support_files",
                side_effect=AssertionError("_download_roblox_support_files should not be called in standard mode"),
            ):
                assert provider._resolve_support_files() == (
                    None,
                    "/tmp/luau-en-us.json",
                )

        download_standard_docs.assert_called_once_with()

    def test_get_or_install_core_dependency_uses_system_binary(self, tmp_path: Path) -> None:
        provider = _make_provider(tmp_path)

        with patch("solidlsp.language_servers.luau_lsp.shutil.which", return_value="/usr/bin/luau-lsp"):
            with patch.object(
                provider,
                "_download_luau_lsp",
                side_effect=AssertionError("_download_luau_lsp should not be called when luau-lsp is on PATH"),
            ):
                assert provider._get_or_install_core_dependency() == "/usr/bin/luau-lsp"

    def test_download_luau_lsp_extracts_binary_into_ls_resources_dir(self, tmp_path: Path) -> None:
        provider = _make_provider(tmp_path)

        def fake_extract(
            url: str,
            target_path: str,
            archive_type: str,
            expected_sha256: str | None = None,
            allowed_hosts: tuple[str, ...] | list[str] | None = None,
        ) -> None:
            del url, archive_type, expected_sha256, allowed_hosts
            nested_dir = Path(target_path) / "nested"
            nested_dir.mkdir(parents=True, exist_ok=True)
            (nested_dir / "luau-lsp").write_text("#!/bin/sh\n", encoding="utf-8")

        with patch("solidlsp.language_servers.luau_lsp.platform.system", return_value="Linux"):
            with patch("solidlsp.language_servers.luau_lsp.platform.machine", return_value="aarch64"):
                with patch(
                    "solidlsp.language_servers.luau_lsp.FileUtils.download_and_extract_archive_verified",
                    side_effect=fake_extract,
                ):
                    binary_path = provider._download_luau_lsp()

        resolved_binary = Path(binary_path)
        assert resolved_binary.exists()
        assert resolved_binary.name == "luau-lsp"
        assert str(resolved_binary).startswith(str(tmp_path))

    def test_download_roblox_support_files_writes_into_ls_resources_dir(self, tmp_path: Path) -> None:
        provider = _make_provider(tmp_path)

        def fake_download(
            url: str, target_path: str, expected_sha256: str | None = None, allowed_hosts: tuple[str, ...] | list[str] | None = None
        ) -> None:
            del expected_sha256, allowed_hosts
            if "type-definitions" in url:
                Path(target_path).write_bytes(b"types")
            else:
                Path(target_path).write_bytes(b"docs")

        with patch("solidlsp.language_servers.luau_lsp.FileUtils.download_file_verified", side_effect=fake_download):
            definitions_path, docs_path = provider._download_roblox_support_files("LocalUserSecurity")

        assert definitions_path == str(tmp_path / "globalTypes.LocalUserSecurity.d.luau")
        assert docs_path == str(tmp_path / "en-us.json")
        assert (tmp_path / "globalTypes.LocalUserSecurity.d.luau").read_bytes() == b"types"
        assert (tmp_path / "en-us.json").read_bytes() == b"docs"

    def test_download_standard_docs_writes_into_ls_resources_dir(self, tmp_path: Path) -> None:
        provider = _make_provider(tmp_path, {"platform": "standard"})

        with patch(
            "solidlsp.language_servers.luau_lsp.FileUtils.download_file_verified",
            side_effect=lambda url, target_path, expected_sha256=None, allowed_hosts=None: Path(target_path).write_bytes(b"docs"),
        ):
            docs_path = provider._download_standard_docs()

        assert docs_path == str(tmp_path / "luau-en-us.json")
        assert (tmp_path / "luau-en-us.json").read_bytes() == b"docs"

    def test_workspace_configuration_uses_configured_platform(self) -> None:
        config = LuauLanguageServer._get_workspace_configuration(SolidLSPSettings.CustomLSSettings({"platform": "standard"}))
        assert config == {"platform": {"type": "standard"}}

    def test_invalid_platform_raises(self, tmp_path: Path) -> None:
        provider = _make_provider(tmp_path, {"platform": "invalid"})

        with pytest.raises(ValueError, match="Unsupported Luau platform"):
            provider._resolve_support_files()

    def test_invalid_roblox_security_level_raises(self, tmp_path: Path) -> None:
        provider = _make_provider(tmp_path, {"roblox_security_level": "invalid"})

        with pytest.raises(ValueError, match="Unsupported Luau Roblox security level"):
            provider._resolve_support_files()
