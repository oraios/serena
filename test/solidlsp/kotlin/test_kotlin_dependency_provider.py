"""Tests for Kotlin Language Server dependency resolution and installation."""

from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import pytest

from solidlsp.dependency_provider import DownloadedDependency, DownloadedDependencyHashDatabase
from solidlsp.language_servers.kotlin_language_server import (
    DEFAULT_KOTLIN_LSP_VERSION,
    INITIAL_KOTLIN_LSP_VERSION,
    KOTLIN_LSP_ALLOWED_HOSTS,
    KotlinLanguageServer,
)
from solidlsp.ls_utils import PlatformId
from solidlsp.settings import SolidLSPSettings


def _make_provider(
    tmp_path: Path,
    custom_settings: dict[str, str] | None = None,
) -> KotlinLanguageServer.DependencyProvider:
    return KotlinLanguageServer.DependencyProvider(
        custom_settings=SolidLSPSettings.CustomLSSettings(custom_settings or {}),
        ls_resources_dir=str(tmp_path),
        project_cache_dir=str(tmp_path / "project-cache"),
    )


@pytest.mark.kotlin
class TestKotlinDependencyProvider:
    @pytest.mark.parametrize(
        ("platform_id", "asset_suffix", "archive_type", "launcher_parts", "sha256"),
        [
            (
                PlatformId.WIN_x64,
                ".win.zip",
                "zip",
                ("bin", "intellij-server.exe"),
                "f2daaa476f26d99301b406f76de6d87c437d04dc72f06845154619d8f991c51f",
            ),
            (
                PlatformId.WIN_arm64,
                "-aarch64.win.zip",
                "zip",
                ("bin", "intellij-server.exe"),
                "73a552a6a420158622e5ad8d96b53da8aa8ced3f88a24fded01575927a2fd8e7",
            ),
            (
                PlatformId.LINUX_x64,
                ".tar.gz",
                "gztar",
                (f"kotlin-server-{DEFAULT_KOTLIN_LSP_VERSION}", "bin", "intellij-server"),
                "2d99d8e198fbe4aa8f4481e37799724ce94803b4ea12a60b416040e3fcd7cc5e",
            ),
            (
                PlatformId.LINUX_arm64,
                "-aarch64.tar.gz",
                "gztar",
                (f"kotlin-server-{DEFAULT_KOTLIN_LSP_VERSION}", "bin", "intellij-server"),
                "2317831c6e5607d05b7ebc1da655330125ce0e3d66fbf24517dfce442debc14e",
            ),
            (
                PlatformId.OSX_x64,
                ".sit",
                "zip",
                (f"kotlin-server-{DEFAULT_KOTLIN_LSP_VERSION}", "bin", "intellij-server"),
                "17369fda97c85418ac24ab38a9df56b21522a3468dfe193832fe455c13920745",
            ),
            (
                PlatformId.OSX_arm64,
                "-aarch64.sit",
                "zip",
                (f"kotlin-server-{DEFAULT_KOTLIN_LSP_VERSION}", "bin", "intellij-server"),
                "6ba6021a706b21e64cef33f7e2b79f187c0910320722bb2d3ed05ad1115ec43f",
            ),
        ],
    )
    def test_default_artifacts_match_jetbrains_release_matrix(
        self,
        tmp_path: Path,
        platform_id: PlatformId,
        asset_suffix: str,
        archive_type: str,
        launcher_parts: tuple[str, ...],
        sha256: str,
    ) -> None:
        artifact = KotlinLanguageServer.DependencyProvider._create_artifact(DEFAULT_KOTLIN_LSP_VERSION, platform_id)
        url = (
            f"https://download-cdn.jetbrains.com/language-server/kotlin-server/{DEFAULT_KOTLIN_LSP_VERSION}/"
            f"kotlin-server-{DEFAULT_KOTLIN_LSP_VERSION}{asset_suffix}"
        )

        with patch("solidlsp.dependency_provider.FileUtils.download_and_extract_archive_verified") as download:
            artifact.dependency.download_to(tmp_path)

        download.assert_called_once_with(
            url,
            str(tmp_path),
            archive_type=archive_type,
            expected_sha256=sha256,
            allowed_hosts=KOTLIN_LSP_ALLOWED_HOSTS,
        )
        assert artifact.launcher_parts == launcher_parts

    @pytest.mark.parametrize(
        ("version", "platform_id", "url", "launcher_parts"),
        [
            (
                "262.2310.0",
                PlatformId.LINUX_x64,
                "https://download-cdn.jetbrains.com/kotlin-lsp/262.2310.0/kotlin-lsp-262.2310.0-linux-x64.zip",
                ("kotlin-lsp.sh",),
            ),
            (
                "262.4739.0",
                PlatformId.LINUX_x64,
                "https://download-cdn.jetbrains.com/kotlin-lsp/262.4739.0/kotlin-server-262.4739.0.tar.gz",
                ("kotlin-server-262.4739.0", "bin", "intellij-server"),
            ),
            (
                "262.8190.0",
                PlatformId.OSX_arm64,
                "https://download-cdn.jetbrains.com/language-server/kotlin-server/262.8190.0/kotlin-server-262.8190.0-aarch64.sit",
                ("kotlin-server-262.8190.0", "bin", "intellij-server"),
            ),
        ],
    )
    def test_version_boundaries_select_the_published_layout(
        self,
        version: str,
        platform_id: PlatformId,
        url: str,
        launcher_parts: tuple[str, ...],
    ) -> None:
        artifact = KotlinLanguageServer.DependencyProvider._create_artifact(version, platform_id)

        assert artifact.dependency.get_url() == url
        assert artifact.launcher_parts == launcher_parts

    def test_custom_versions_skip_hash_lookup_by_design(self, tmp_path: Path) -> None:
        artifact = KotlinLanguageServer.DependencyProvider._create_artifact("262.8190.1", PlatformId.LINUX_x64)

        with (
            patch(
                "solidlsp.dependency_provider.DownloadedDependencyHashDatabase.get_instance",
                side_effect=AssertionError("custom versions must not consult the pinned hash database"),
            ),
            patch("solidlsp.dependency_provider.FileUtils.download_and_extract_archive_verified") as download,
        ):
            artifact.dependency.download_to(tmp_path)

        download.assert_called_once_with(
            "https://download-cdn.jetbrains.com/language-server/kotlin-server/262.8190.1/kotlin-server-262.8190.1.tar.gz",
            str(tmp_path),
            archive_type="gztar",
            expected_sha256=None,
            allowed_hosts=KOTLIN_LSP_ALLOWED_HOSTS,
        )

    def test_hash_updater_registers_frozen_and_default_artifacts(self) -> None:
        updated_asset_names: list[str] = []

        class RecordingUpdater:
            def update(self, dependency: DownloadedDependency) -> None:
                updated_asset_names.append(dependency.get_url().rsplit("/", 1)[-1])

        with patch.object(DownloadedDependencyHashDatabase, "get_instance") as get_hash_database:
            get_hash_database.return_value.update_context.return_value = nullcontext(RecordingUpdater())
            KotlinLanguageServer.DependencyProvider.update_dep_hashes()

        assert set(updated_asset_names) == {
            "kotlin-lsp-261.13587.0-win-x64.zip",
            "kotlin-lsp-261.13587.0-linux-x64.zip",
            "kotlin-lsp-261.13587.0-linux-aarch64.zip",
            "kotlin-lsp-261.13587.0-mac-x64.zip",
            "kotlin-lsp-261.13587.0-mac-aarch64.zip",
            "kotlin-server-262.9593.0.win.zip",
            "kotlin-server-262.9593.0-aarch64.win.zip",
            "kotlin-server-262.9593.0.tar.gz",
            "kotlin-server-262.9593.0-aarch64.tar.gz",
            "kotlin-server-262.9593.0.sit",
            "kotlin-server-262.9593.0-aarch64.sit",
        }

    @pytest.mark.parametrize(
        ("settings", "platform_id", "relative_launcher", "expected_directory"),
        [
            (
                {"kotlin_lsp_version": INITIAL_KOTLIN_LSP_VERSION},
                PlatformId.LINUX_x64,
                ("kotlin-lsp.sh",),
                "kotlin_language_server",
            ),
            (
                {},
                PlatformId.LINUX_arm64,
                (f"kotlin-server-{DEFAULT_KOTLIN_LSP_VERSION}", "bin", "intellij-server"),
                f"kotlin_language_server-{DEFAULT_KOTLIN_LSP_VERSION}",
            ),
        ],
    )
    def test_installs_pinned_versions_in_compatible_directories(
        self,
        tmp_path: Path,
        settings: dict[str, str],
        platform_id: PlatformId,
        relative_launcher: tuple[str, ...],
        expected_directory: str,
    ) -> None:
        provider = _make_provider(tmp_path, settings)

        def fake_download(
            _url: str,
            target_path: str,
            archive_type: str,
            expected_sha256: str | None = None,
            allowed_hosts: tuple[str, ...] | list[str] | None = None,
        ) -> None:
            del archive_type, expected_sha256, allowed_hosts
            launcher = Path(target_path).joinpath(*relative_launcher)
            launcher.parent.mkdir(parents=True, exist_ok=True)
            launcher.write_text("#!/bin/sh\n", encoding="utf-8")

        with (
            patch(
                "solidlsp.language_servers.kotlin_language_server.PlatformUtils.get_platform_id",
                return_value=platform_id,
            ),
            patch(
                "solidlsp.dependency_provider.FileUtils.download_and_extract_archive_verified",
                side_effect=fake_download,
            ),
        ):
            launcher_path = provider._get_or_install_core_dependency()

        assert launcher_path == str((tmp_path / expected_directory).joinpath(*relative_launcher))

    @pytest.mark.parametrize(
        ("platform_id", "modern_launcher", "other_os_launcher"),
        [
            (PlatformId.LINUX_x64, "/path/to/intellij-server", "/path/to/intellij-server.exe"),
            (PlatformId.WIN_x64, "/path/to/intellij-server.exe", "/path/to/intellij-server"),
        ],
    )
    def test_custom_launcher_arguments_use_the_active_os_name(
        self,
        tmp_path: Path,
        platform_id: PlatformId,
        modern_launcher: str,
        other_os_launcher: str,
    ) -> None:
        modern_provider = _make_provider(tmp_path, {"ls_path": modern_launcher})
        other_os_provider = _make_provider(tmp_path, {"ls_path": other_os_launcher})

        with patch(
            "solidlsp.language_servers.kotlin_language_server.PlatformUtils.get_platform_id",
            return_value=platform_id,
        ):
            assert modern_provider.create_launch_command() == [
                modern_launcher,
                "--stdio",
                "--system-path",
                str(tmp_path / "project-cache" / "kotlin-lsp-system"),
            ]
            assert other_os_provider.create_launch_command() == [other_os_launcher, "--stdio"]

    def test_invalid_version_is_rejected_before_download(self) -> None:
        with pytest.raises(ValueError, match="dot-separated integers"):
            KotlinLanguageServer.DependencyProvider._create_artifact("latest", PlatformId.OSX_arm64)

    def test_unsupported_modern_platform_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unsupported platform"):
            KotlinLanguageServer.DependencyProvider._create_artifact(DEFAULT_KOTLIN_LSP_VERSION, PlatformId.LINUX_x86)
